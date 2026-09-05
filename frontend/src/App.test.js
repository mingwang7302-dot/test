import { render, screen } from '@testing-library/react';
import App from './App';

test('renders Taiwan market dashboard title', () => {
  render(<App />);
  expect(screen.getByText(/台股籌碼與估值工作台/i)).toBeInTheDocument();
});
