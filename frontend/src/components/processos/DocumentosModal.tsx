import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { FileText, Trash2, Upload } from 'lucide-react';
import { getApiError } from '../../services/api';
import { processoService } from '../../services/juripredict';
import type { DocumentoProcesso, Processo } from '../../types';
import ConfirmDialog from '../ui/ConfirmDialog';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';

type DocumentosModalProps = {
  processo: Processo | null;
  onClose: () => void;
};

const formatarTamanho = (bytes: number) => (
  bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`
);

const formatarData = (valor: string) => new Intl.DateTimeFormat('pt-BR').format(new Date(valor));

const DocumentosModal = ({ processo, onClose }: DocumentosModalProps) => {
  const [documentos, setDocumentos] = useState<DocumentoProcesso[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [excluindo, setExcluindo] = useState<DocumentoProcesso | null>(null);
  const seletor = useRef<HTMLInputElement>(null);

  const id = processo?.id;
  useEffect(() => {
    if (id === undefined) return;
    let ativo = true;
    setDocumentos([]);
    setErro('');
    setLoading(true);
    processoService.documentos(id)
      .then((lista) => { if (ativo) setDocumentos(lista); })
      .catch((requestError) => { if (ativo) setErro(getApiError(requestError)); })
      .finally(() => { if (ativo) setLoading(false); });
    return () => { ativo = false; };
  }, [id]);

  const enviar = async (event: ChangeEvent<HTMLInputElement>) => {
    const arquivo = event.target.files?.[0];
    event.target.value = '';
    if (!arquivo || id === undefined) return;
    setBusy(true);
    setErro('');
    try {
      const criado = await processoService.anexarDocumento(id, arquivo);
      setDocumentos((atual) => [criado, ...atual]);
    } catch (requestError) {
      setErro(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const excluir = async () => {
    if (!excluindo || id === undefined) return;
    setBusy(true);
    setErro('');
    try {
      await processoService.removerDocumento(id, excluindo.id);
      setDocumentos((atual) => atual.filter((item) => item.id !== excluindo.id));
      setExcluindo(null);
    } catch (requestError) {
      setErro(getApiError(requestError));
      setExcluindo(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Modal
        open={Boolean(processo)}
        title="Documentos"
        description={processo ? `Processo ${processo.numero_cnj}. PDF, DOC ou DOCX.` : undefined}
        size="large"
        onClose={() => !busy && onClose()}
      >
        <div className="andamentos">
          <div className="andamentos__topo">
            <small>{documentos.length === 1 ? '1 documento' : `${documentos.length} documentos`}</small>
            <button
              className="button button--secondary button--small"
              type="button"
              onClick={() => seletor.current?.click()}
              disabled={busy}
            >
              <Upload size={14} /> {busy ? 'Enviando...' : 'Anexar documento'}
            </button>
            <input
              ref={seletor}
              type="file"
              accept=".pdf,.doc,.docx"
              aria-label="Selecionar documento"
              hidden
              onChange={enviar}
            />
          </div>

          {erro && <Feedback type="error">{erro}</Feedback>}
          {loading && <Feedback type="info">Carregando...</Feedback>}
          {!loading && documentos.length === 0 && (
            <p className="andamentos__vazio">Nenhum documento anexado a este processo.</p>
          )}

          {documentos.length > 0 && (
            <ul className="documentos__lista">
              {documentos.map((item) => (
                <li key={item.id}>
                  <FileText size={16} aria-hidden="true" />
                  <a href={item.url} target="_blank" rel="noreferrer">{item.nome}</a>
                  <small>
                    {formatarTamanho(item.tamanho)} · {formatarData(item.criado_em)}
                    {item.enviado_por_nome ? ` · ${item.enviado_por_nome}` : ''}
                  </small>
                  <button
                    className="action-button action-button--danger"
                    type="button"
                    aria-label={`Excluir documento ${item.nome}`}
                    onClick={() => setExcluindo(item)}
                    disabled={busy}
                  >
                    <Trash2 size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(excluindo)}
        title="Excluir documento"
        message={`Deseja excluir "${excluindo?.nome ?? ''}"? O arquivo será apagado.`}
        busy={busy}
        onCancel={() => setExcluindo(null)}
        onConfirm={excluir}
      />
    </>
  );
};

export default DocumentosModal;
