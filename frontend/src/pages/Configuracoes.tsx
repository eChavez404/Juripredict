import { useState, type FormEvent } from 'react';
import { KeyRound, Save, UserRound } from 'lucide-react';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import { useAuth } from '../contexts/auth';
import { getApiError } from '../services/api';
import { authService } from '../services/juripredict';

const Configuracoes = () => {
  const { user, updateUser } = useAuth();
  const [profile, setProfile] = useState({ nome: user?.nome ?? '', email: user?.email ?? '' });
  const [passwords, setPasswords] = useState({ senha_atual: '', nova_senha: '', confirmacao: '' });
  const [profileFeedback, setProfileFeedback] = useState<{ type: 'error' | 'success'; text: string } | null>(null);
  const [passwordFeedback, setPasswordFeedback] = useState<{ type: 'error' | 'success'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setProfileFeedback(null);
    try {
      const updated = await authService.updateMe(profile);
      updateUser(updated);
      setProfileFeedback({ type: 'success', text: 'Perfil atualizado com sucesso.' });
    } catch (requestError) {
      setProfileFeedback({ type: 'error', text: getApiError(requestError) });
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordFeedback(null);
    if (passwords.nova_senha !== passwords.confirmacao) {
      setPasswordFeedback({ type: 'error', text: 'A confirmação da nova senha não confere.' });
      return;
    }
    setBusy(true);
    try {
      const response = await authService.changePassword(passwords.senha_atual, passwords.nova_senha);
      setPasswords({ senha_atual: '', nova_senha: '', confirmacao: '' });
      setPasswordFeedback({ type: 'success', text: response.detail });
    } catch (requestError) {
      setPasswordFeedback({ type: 'error', text: getApiError(requestError) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader eyebrow="Conta" title="Configurações" description="Atualize seus dados de acesso e informações de perfil." />
      <section className="settings-grid">
        <article className="panel panel--padded settings-card">
          <div className="section-heading"><div><h2><UserRound size={18} /> Perfil</h2><p>Informações exibidas no sistema</p></div></div>
          <form className="entity-form" onSubmit={saveProfile}>
            {profileFeedback && <Feedback type={profileFeedback.type}>{profileFeedback.text}</Feedback>}
            <label className="form-field"><span>Usuário</span><input value={user?.username ?? ''} disabled /></label>
            <label className="form-field"><span>Nome</span><input value={profile.nome} onChange={(event) => setProfile({ ...profile, nome: event.target.value })} required /></label>
            <label className="form-field"><span>E-mail</span><input type="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} required /></label>
            <div className="form-actions"><button className="button button--primary" type="submit" disabled={busy}><Save size={16} /> Salvar perfil</button></div>
          </form>
        </article>

        <article className="panel panel--padded settings-card">
          <div className="section-heading"><div><h2><KeyRound size={18} /> Segurança</h2><p>Use pelo menos oito caracteres</p></div></div>
          <form className="entity-form" onSubmit={changePassword}>
            {passwordFeedback && <Feedback type={passwordFeedback.type}>{passwordFeedback.text}</Feedback>}
            <label className="form-field"><span>Senha atual</span><input type="password" autoComplete="current-password" value={passwords.senha_atual} onChange={(event) => setPasswords({ ...passwords, senha_atual: event.target.value })} required /></label>
            <label className="form-field"><span>Nova senha</span><input type="password" minLength={8} autoComplete="new-password" value={passwords.nova_senha} onChange={(event) => setPasswords({ ...passwords, nova_senha: event.target.value })} required /></label>
            <label className="form-field"><span>Confirmar nova senha</span><input type="password" minLength={8} autoComplete="new-password" value={passwords.confirmacao} onChange={(event) => setPasswords({ ...passwords, confirmacao: event.target.value })} required /></label>
            <div className="form-actions"><button className="button button--primary" type="submit" disabled={busy}>Alterar senha</button></div>
          </form>
        </article>
      </section>
    </div>
  );
};

export default Configuracoes;
