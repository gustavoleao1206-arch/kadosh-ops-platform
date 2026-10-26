import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'
import './index.css'
import { router } from './app/router'
import { ApiError } from './api/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // repete uma vez só erros de rede/servidor; 401/403/404/422 não mudam ao repetir
      retry: (count, err) => count < 1 && !(err instanceof ApiError && err.status < 500),
      staleTime: 15_000,
      refetchOnWindowFocus: true, // "quase tempo real": ao voltar para a aba, recarrega
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
