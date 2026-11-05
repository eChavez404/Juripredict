import LegalPage, { type LegalSection } from '../components/legal/LegalPage';
import { CONTATO_PRIVACIDADE } from '../features/legal/config';

const secoes: LegalSection[] = [
  {
    titulo: 'Quem trata os dados',
    conteudo: (
      <>
        <p>
          Para os dados da sua conta (nome, e-mail e senha), o JuriPredict é o controlador. Para os
          dados que o escritório cadastra sobre seus clientes e processos, o controlador é o próprio
          escritório, e o JuriPredict os trata como operador, conforme as instruções dele.
        </p>
        <p>
          Por isso, pedidos sobre dados de clientes e de processos devem ser feitos ao escritório
          responsável.
        </p>
      </>
    ),
  },
  {
    titulo: 'Quais dados tratamos',
    conteudo: (
      <ul>
        <li><strong>Conta:</strong> nome, e-mail e senha. A senha é guardada apenas como resumo irreversível (hash).</li>
        <li><strong>Escritório:</strong> nome, fuso horário, integrantes da equipe e o papel de cada um.</li>
        <li>
          <strong>Dados cadastrados pelo escritório:</strong> clientes (nome, CPF ou CNPJ, e-mail e telefone),
          processos (número, partes, valor, observações e petição inicial enviada) e agenda.
        </li>
        <li><strong>Histórico de atividade:</strong> quem fez cada alteração no escritório e quando.</li>
        <li><strong>Aceite dos termos:</strong> a versão aceita, a data e o endereço IP no momento do aceite.</li>
      </ul>
    ),
  },
  {
    titulo: 'Para que usamos',
    conteudo: (
      <ul>
        <li>Prestar o serviço de gestão do escritório.</li>
        <li>Proteger as contas e manter o histórico de atividade para auditoria.</li>
        <li>
          Enviar mensagens do próprio serviço: convites para a equipe, recuperação de senha e lembretes
          de prazos e audiências.
        </li>
      </ul>
    ),
  },
  {
    titulo: 'Como protegemos',
    conteudo: (
      <ul>
        <li>CPF e CNPJ de clientes são guardados criptografados.</li>
        <li>As conexões usam HTTPS.</li>
        <li>As tentativas de entrada são limitadas e as sessões podem ser encerradas no servidor.</li>
        <li>Cada escritório enxerga apenas os próprios dados.</li>
        <li>O histórico de atividade não pode ser alterado nem apagado.</li>
      </ul>
    ),
  },
  {
    titulo: 'Agentes e integrações (tokens de API)',
    conteudo: (
      <>
        <p>
          Você pode criar tokens que permitem a um agente de inteligência artificial consultar, somente
          para leitura, processos, andamentos, agenda e indicadores do seu escritório. Ao usar um token,
          os dados consultados são enviados ao agente e ao provedor do modelo que você escolheu, fora do
          JuriPredict. Essa escolha e a responsabilidade por ela são do escritório.
        </p>
        <ul>
          <li>Os tokens não acessam dados de clientes (como CPF ou CNPJ), arquivos nem a equipe.</li>
          <li>Cada consulta feita com um token fica registrada na auditoria do escritório (o que foi consultado e quando; os termos buscados não são gravados).</li>
          <li>Você pode revogar um token a qualquer momento, e trocar a senha ou excluir a conta revoga todos.</li>
        </ul>
      </>
    ),
  },
  {
    titulo: 'Com quem os dados passam',
    conteudo: (
      <>
        <p>Para funcionar, o serviço depende de provedores de infraestrutura que processam dados em nosso nome:</p>
        <ul>
          <li>hospedagem da aplicação e banco de dados;</li>
          <li>armazenamento dos arquivos enviados;</li>
          <li>envio de e-mail;</li>
          <li>monitoramento de erros, quando ativado. O conteúdo das requisições nunca é enviado a ele.</li>
        </ul>
      </>
    ),
  },
  {
    titulo: 'Cookies e armazenamento no navegador',
    conteudo: (
      <p>
        Não usamos cookies de publicidade nem ferramentas de análise de comportamento. O navegador guarda
        apenas o necessário para manter você conectado.
      </p>
    ),
  },
  {
    titulo: 'Por quanto tempo guardamos',
    conteudo: (
      <>
        <p>
          Ao excluir a conta, seu nome, e-mail e senha são removidos e o acesso é encerrado. O histórico do
          escritório é preservado sem identificar você, e o registro do aceite dos termos permanece como prova.
        </p>
        <p>
          Se você era a única pessoa do escritório, ele é desativado, mas os dados de clientes são mantidos
          pelo prazo de guarda aplicável à atividade profissional, até pedido de exclusão pelo responsável.
        </p>
      </>
    ),
  },
  {
    titulo: 'Seus direitos',
    conteudo: (
      <>
        <p>
          Em Configurações, na área de privacidade, você pode baixar uma cópia dos seus dados e excluir a
          conta. Também pode corrigir nome e e-mail no perfil.
        </p>
        <p>
          Para outros pedidos previstos na LGPD, entre em contato
          {CONTATO_PRIVACIDADE
            ? <> pelo e-mail <a href={`mailto:${CONTATO_PRIVACIDADE}`}>{CONTATO_PRIVACIDADE}</a>.</>
            : <> pelo canal de suporte indicado no seu contrato.</>}
        </p>
      </>
    ),
  },
  {
    titulo: 'Mudanças neste texto',
    conteudo: (
      <p>
        Quando este texto mudar, a versão acima muda também, e pediremos um novo aceite quando a alteração
        for relevante.
      </p>
    ),
  },
];

const Privacidade = () => <LegalPage titulo="Política de Privacidade" secoes={secoes} />;

export default Privacidade;
