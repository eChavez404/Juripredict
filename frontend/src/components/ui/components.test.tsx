import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Brand from './Brand';
import SearchField from './SearchField';

describe('componentes compartilhados', () => {
  it('apresenta a marca e sua descrição', () => {
    render(<Brand />);

    expect(screen.getByText('Inteligência jurídica')).toBeInTheDocument();
    expect(screen.getByText('Predict')).toBeInTheDocument();
  });

  it('propaga alterações do campo de busca', () => {
    const onChange = vi.fn();
    render(
      <SearchField
        value=""
        onChange={onChange}
        placeholder="Buscar processos"
        label="Buscar processos"
      />,
    );

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar processos' }), {
      target: { value: '0010234' },
    });

    expect(onChange).toHaveBeenCalledWith('0010234');
  });
});
