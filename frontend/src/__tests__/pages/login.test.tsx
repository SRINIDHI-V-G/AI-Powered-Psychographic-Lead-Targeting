import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  usePathname: () => '/login',
}));

// Mock tanstack query
jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ clear: jest.fn() }),
}));

// Mock API
jest.mock('@/lib/api/client', () => ({
  default: {
    get: jest.fn().mockResolvedValue({ data: { id: '1', name: 'Test Company' } }),
  },
}));

jest.mock('@/lib/api/demo', () => ({
  setupDemo: jest.fn().mockResolvedValue({
    api_key: 'demo-key',
    product_id: 'demo-product',
    company_id: 'demo-company',
    status: 'ok',
  }),
}));

import LoginPage from '@/app/login/page';

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the login form', () => {
    render(<LoginPage />);
    expect(screen.getByText('PsychoLead AI')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('pl_xxxxxxxxxxxxxxxx')).toBeInTheDocument();
    expect(screen.getByText('Connect')).toBeInTheDocument();
  });

  it('renders the Demo Mode button', () => {
    render(<LoginPage />);
    expect(screen.getByText('Try Demo Mode')).toBeInTheDocument();
  });

  it('shows error state on empty key submission', async () => {
    render(<LoginPage />);
    const button = screen.getByText('Connect');
    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.getByText(/cannot be empty/i)).toBeInTheDocument();
    });
  });

  it('toggles password visibility', async () => {
    render(<LoginPage />);
    const input = screen.getByPlaceholderText('pl_xxxxxxxxxxxxxxxx');
    expect(input).toHaveAttribute('type', 'password');

    const toggleBtn = input.parentElement?.querySelector('button');
    if (toggleBtn) {
      fireEvent.click(toggleBtn);
      expect(input).toHaveAttribute('type', 'text');
    }
  });

  it('allows typing in the API key field', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    const input = screen.getByPlaceholderText('pl_xxxxxxxxxxxxxxxx');
    await user.type(input, 'my-test-key');
    expect(input).toHaveValue('my-test-key');
  });
});
