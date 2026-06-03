import { render, screen } from '@testing-library/react';
import { OceanBars } from '@/components/charts/OceanBars';

const sampleData = {
  openness: 70,
  conscientiousness: 60,
  extraversion: 55,
  agreeableness: 80,
  neuroticism: 40,
};

describe('OceanBars', () => {
  it('renders all 5 OCEAN dimensions', () => {
    render(<OceanBars data={sampleData} />);
    expect(screen.getByText('Openness')).toBeInTheDocument();
    expect(screen.getByText('Conscientiousness')).toBeInTheDocument();
    expect(screen.getByText('Extraversion')).toBeInTheDocument();
    expect(screen.getByText('Agreeableness')).toBeInTheDocument();
    expect(screen.getByText('Neuroticism')).toBeInTheDocument();
  });

  it('displays correct score values (divided by 10)', () => {
    render(<OceanBars data={sampleData} />);
    expect(screen.getByText('7.0')).toBeInTheDocument();
    expect(screen.getByText('6.0')).toBeInTheDocument();
    expect(screen.getByText('5.5')).toBeInTheDocument();
    expect(screen.getByText('8.0')).toBeInTheDocument();
    expect(screen.getByText('4.0')).toBeInTheDocument();
  });

  it('renders compact mode with short labels', () => {
    render(<OceanBars data={sampleData} compact />);
    expect(screen.getByText('O')).toBeInTheDocument();
    expect(screen.getByText('C')).toBeInTheDocument();
    expect(screen.getByText('E')).toBeInTheDocument();
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('N')).toBeInTheDocument();
  });

  it('compact mode does not show numeric values', () => {
    render(<OceanBars data={sampleData} compact />);
    expect(screen.queryByText('7.0')).not.toBeInTheDocument();
  });

  it('renders 5 progress bar tracks', () => {
    const { container } = render(<OceanBars data={sampleData} />);
    const bars = container.querySelectorAll('.bg-slate-100.rounded-full');
    expect(bars.length).toBe(5);
  });
});
