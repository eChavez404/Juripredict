import Modal from './Modal';

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

const ConfirmDialog = ({ open, title, message, busy, onCancel, onConfirm }: ConfirmDialogProps) => (
  <Modal open={open} title={title} onClose={onCancel}>
    <p className="confirm-copy">{message}</p>
    <div className="form-actions">
      <button className="button button--secondary" type="button" onClick={onCancel} disabled={busy}>
        Cancelar
      </button>
      <button className="button button--danger" type="button" onClick={onConfirm} disabled={busy}>
        {busy ? 'Excluindo...' : 'Excluir'}
      </button>
    </div>
  </Modal>
);

export default ConfirmDialog;
