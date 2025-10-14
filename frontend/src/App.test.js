import { render, screen } from '@testing-library/react';
import App from './App';

test('renders main title', () => {
  render(<App />);
  const titleElement = screen.getByText(/AI 股價分析與估值工具/i);
  expect(titleElement).toBeInTheDocument();
});
