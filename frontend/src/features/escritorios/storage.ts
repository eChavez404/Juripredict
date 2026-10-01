export const ACTIVE_ESCRITORIO_STORAGE_KEY = 'juripredict_active_escritorio_id';

export const getStoredEscritorioId = (): string | null => {
  const rawValue = localStorage.getItem(ACTIVE_ESCRITORIO_STORAGE_KEY);
  return rawValue?.trim() || null;
};

export const setStoredEscritorioId = (id: string | null) => {
  if (id === null) {
    localStorage.removeItem(ACTIVE_ESCRITORIO_STORAGE_KEY);
    return;
  }
  localStorage.setItem(ACTIVE_ESCRITORIO_STORAGE_KEY, id);
};
