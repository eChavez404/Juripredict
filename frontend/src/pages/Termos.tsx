import { Link } from 'react-router-dom';
import LegalPage, { type LegalSection } from '../components/legal/LegalPage';

const secoes: LegalSection[] = [
  {
    titulo: 'O serviço',
    conteudo: (
      <p>
        O JuriPredict é uma plataforma de gestão para escritórios de advocacia: clientes, processos, agenda,
        equipe e indicadores de jurimetria calculados a partir dos dados do próprio escritório.
      </p>
    ),
  },
  {
    titulo: 'Conta e responsabilidades',
    conteudo: (
      <ul>
        <li>Você é responsável por manter a senha em sigilo e por tudo o que for feito com a sua conta.</li>
        <li>O proprietário do escritório responde pelas pessoas que convida e pelos papéis que concede.</li>
        <li>
          O sigilo profissional sobre os dados dos clientes continua sendo responsabilidade do escritório e
          dos advogados que o integram.
        </li>
        <li>As informações do cadastro devem ser verdadeiras e mantidas atualizadas.</li>
      </ul>
    ),
  },
  {
    titulo: 'Conteúdo do escritório',
    conteudo: (
      <p>
        Os dados e os arquivos cadastrados continuam sendo do escritório. Ao usar o serviço, o escritório nos
        autoriza a armazená-los e processá-los apenas para operar a plataforma. O tratamento está descrito na{' '}
        <Link to="/privacidade">Política de Privacidade</Link>.
      </p>
    ),
  },
  {
    titulo: 'Jurimetria não é garantia',
    conteudo: (
      <p>
        Os indicadores são estatísticas descritivas e dependem da qualidade e da quantidade dos dados
        cadastrados. Eles apoiam a decisão do advogado, mas não são aconselhamento jurídico nem garantia de
        resultado de qualquer processo. Indicadores calculados sobre poucos casos têm pouca confiabilidade.
      </p>
    ),
  },
  {
    titulo: 'Uso permitido',
    conteudo: (
      <ul>
        <li>É proibido tentar acessar dados de outro escritório ou contornar os controles de segurança.</li>
        <li>É proibido usar o serviço para fins ilícitos ou enviar conteúdo malicioso.</li>
        <li>É proibido sobrecarregar o serviço com uso automatizado não autorizado.</li>
      </ul>
    ),
  },
  {
    titulo: 'Disponibilidade',
    conteudo: (
      <p>
        Trabalhamos para manter o serviço disponível, mas podem ocorrer interrupções para manutenção ou por
        falhas de terceiros. Mantenha cópia do que for crítico para o escritório.
      </p>
    ),
  },
  {
    titulo: 'Encerramento',
    conteudo: (
      <p>
        Você pode excluir a conta a qualquer momento em Configurações. Podemos suspender contas que violem
        estes termos. As consequências da exclusão para os dados estão na Política de Privacidade.
      </p>
    ),
  },
  {
    titulo: 'Mudanças nestes termos',
    conteudo: (
      <p>
        Quando estes termos mudarem, a versão indicada acima muda também. O uso continuado depois da
        mudança, ou um novo aceite quando exigido, indica concordância com o novo texto.
      </p>
    ),
  },
];

const Termos = () => <LegalPage titulo="Termos de Uso" secoes={secoes} />;

export default Termos;
