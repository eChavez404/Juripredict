// Mantenha igual a TERMOS_VERSAO do backend (settings.py). Mudou o texto das
// páginas jurídicas, mude a versão nos dois lugares: o cadastro grava qual
// versão cada pessoa aceitou.
export const TERMOS_VERSAO = '2026-10';

// Contato para pedidos de titulares (LGPD). Defina VITE_CONTATO_PRIVACIDADE no
// build; sem ele, a página orienta a usar o canal do contrato.
export const CONTATO_PRIVACIDADE: string | undefined =
  import.meta.env.VITE_CONTATO_PRIVACIDADE || undefined;
