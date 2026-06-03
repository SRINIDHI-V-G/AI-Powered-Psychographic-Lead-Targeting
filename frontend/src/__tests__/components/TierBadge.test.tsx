import { render, screen } from '@testing-library/react';
import { TierBadge } from '@/components/shared/TierBadge';

describe('TierBadge', () => {
  it('renders Hot tier for score >= 75', () => {
    render(<TierBadge score={80} />);
    expect(screen.getByText(/Hot/)).toBeInTheDocument();
  });

  it('renders Warm tier for score >= 50 and < 75', () => {
    render(<TierBadge score={60} />);
    expect(screen.getByText(/Warm/)).toBeInTheDocument();
  });

  it('renders Cold tier for score < 50', () => {
    render(<TierBadge score={30} />);
    expect(screen.getByText(/Cold/)).toBeInTheDocument();
  });

  it('renders exact boundary: 75 is Hot', () => {
    render(<TierBadge score={75} />);
    expect(screen.getByText(/Hot/)).toBeInTheDocument();
  });

  it('renders exact boundary: 50 is Warm', () => {
    render(<TierBadge score={50} />);
    expect(screen.getByText(/Warm/)).toBeInTheDocument();
  });

  it('renders exact boundary: 49 is Cold', () => {
    render(<TierBadge score={49} />);
    expect(screen.getByText(/Cold/)).toBeInTheDocument();
  });

  it('accepts explicit tier prop', () => {
    render(<TierBadge tier="Hot" />);
    expect(screen.getByText(/Hot/)).toBeInTheDocument();
  });

  it('applies correct color class for Hot', () => {
    const { container } = render(<TierBadge score={80} />);
    expect(container.firstChild).toHaveClass('bg-red-100');
  });

  it('applies correct color class for Warm', () => {
    const { container } = render(<TierBadge score={60} />);
    expect(container.firstChild).toHaveClass('bg-orange-100');
  });

  it('applies correct color class for Cold', () => {
    const { container } = render(<TierBadge score={20} />);
    expect(container.firstChild).toHaveClass('bg-blue-100');
  });
});
