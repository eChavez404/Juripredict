import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Brand from './Brand';
import PageHeader from './PageHeader';
import SearchField from './SearchField';
import ViewToggle from './ViewToggle';

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

  it('permite alternar a visualização para cards', () => {
    const onChange = vi.fn();
    render(<ViewToggle value="table" onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'Cards' }));

    expect(onChange).toHaveBeenCalledWith('cards');
    expect(screen.getByRole('button', { name: 'Tabela' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('navega para o destino configurado no botão de voltar', () => {
    render(
      <MemoryRouter initialEntries={['/processos']}>
        <Routes>
          <Route path="/" element={<span>Painel principal</span>} />
          <Route path="/processos" element={<PageHeader title="Processos" backTo="/" />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Voltar' }));

    expect(screen.getByText('Painel principal')).toBeInTheDocument();
  });
});
