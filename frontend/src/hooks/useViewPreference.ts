import { useEffect, useState } from 'react';
import type { CollectionView } from '../components/ui/ViewToggle';

const readPreference = (storageKey: string, fallback: CollectionView): CollectionView => {
  try {
    const stored = window.localStorage.getItem(storageKey);
    if (stored === 'table' || stored === 'cards') return stored;
    return typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 760px)').matches
      ? 'cards'
      : fallback;
  } catch {
    return fallback;
  }
};

const useViewPreference = (storageKey: string, fallback: CollectionView = 'table') => {
  const [view, setView] = useState<CollectionView>(() => readPreference(storageKey, fallback));

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, view);
    } catch {
      // A preferência é opcional quando o armazenamento do navegador não está disponível.
    }
  }, [storageKey, view]);

  return [view, setView] as const;
};

export default useViewPreference;
