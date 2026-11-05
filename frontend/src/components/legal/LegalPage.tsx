import type { ReactNode } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import Brand from '../ui/Brand';
import { TERMOS_VERSAO } from '../../features/legal/config';

export type LegalSection = { titulo: string; conteudo: ReactNode };

type LegalPageProps = { titulo: string; secoes: LegalSection[] };

/** Estrutura comum dos Termos de Uso e da Política de Privacidade. */
const LegalPage = ({ titulo, secoes }: LegalPageProps) => (
  <main className="legal-page">
    <header className="legal-page__header">
      <Brand />
      <Link className="text-link" to="/login"><ArrowLeft size={14} aria-hidden="true" /> Voltar</Link>
    </header>

    <article className="legal-page__body">
      <h1>{titulo}</h1>
      <p className="legal-page__meta">Versão {TERMOS_VERSAO}</p>

      <p className="legal-page__notice" role="note">
        Texto em revisão. Esta versão descreve, de forma técnica, como o sistema funciona hoje. A
        redação jurídica definitiva deve ser validada por um advogado antes do lançamento comercial.
      </p>

      {secoes.map((secao, indice) => (
        <section key={secao.titulo}>
          <h2>{indice + 1}. {secao.titulo}</h2>
          {secao.conteudo}
        </section>
      ))}
    </article>
  </main>
);

export default LegalPage;
