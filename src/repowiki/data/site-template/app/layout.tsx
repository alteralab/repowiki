import { Provider } from '@/components/provider';
import './global.css';

// No next/font/google: offline builds fail hard when fonts.googleapis.com is unreachable.
// System stack with Korean fallbacks (Pretendard if installed, else OS Korean fonts).
export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="ko" className="font-sans" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
