import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router'
import { AuthProvider, useAuth } from './auth'
import { ToastProvider, Spinner } from '../components/ui'
import { AppShell } from './layout/AppShell'
import { LoginPage } from '../features/login/LoginPage'
import { ChangePasswordPage } from '../features/login/ChangePasswordPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { ClientsPage } from '../features/clients/ClientsPage'
import { ClientDetailPage } from '../features/clients/ClientDetailPage'
import { VehiclesPage } from '../features/vehicles/VehiclesPage'
import { VehicleDetailPage } from '../features/vehicles/VehicleDetailPage'
import { UsersPage } from '../features/settings/UsersPage'
import { ServicesPage } from '../features/catalog/ServicesPage'
import { AgendaPage } from '../features/agenda/AgendaPage'
import { WorkOrdersPage } from '../features/work-orders/WorkOrdersPage'
import { CaixaPage } from '../features/finance/CaixaPage'
import { CobrancasPage } from '../features/finance/CobrancasPage'
import { ExtratoPage } from '../features/finance/ExtratoPage'
import { FinanceLayout } from '../features/finance/FinanceLayout'
import { ReportsPage } from '../features/reports/ReportsPage'
import { WorkOrderPage } from '../features/work-orders/WorkOrderPage'
import { ErrorPage } from './ErrorPage'

function Providers() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Outlet />
      </ToastProvider>
    </AuthProvider>
  )
}

/** Só entra quem tem sessão; quem precisa trocar a senha vai direto para a tela de troca. */
function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Spinner label="Abrindo o painel…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (user.must_change_password && location.pathname !== '/trocar-senha') return <Navigate to="/trocar-senha" replace />
  return <Outlet />
}

function RequireAdmin() {
  const { user } = useAuth()
  if (user?.role !== 'admin') return <Navigate to="/" replace />
  return <Outlet />
}

export const router = createBrowserRouter([
  {
    element: <Providers />,
    errorElement: <ErrorPage />,
    children: [
      { path: '/login', element: <LoginPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: '/trocar-senha', element: <ChangePasswordPage /> },
          {
            element: <AppShell />,
            children: [
              { path: '/', element: <DashboardPage /> },
              { path: '/clientes', element: <ClientsPage /> },
              { path: '/clientes/:id', element: <ClientDetailPage /> },
              { path: '/veiculos', element: <VehiclesPage /> },
              { path: '/veiculos/:id', element: <VehicleDetailPage /> },
              { path: '/servicos', element: <ServicesPage /> },
              { path: '/agenda', element: <AgendaPage /> },
              { path: '/os', element: <WorkOrdersPage /> },
              { path: '/os/:id', element: <WorkOrderPage /> },
              {
                path: '/financeiro',
                element: <FinanceLayout />,
                children: [
                  { index: true, element: <CaixaPage /> },
                  { path: 'extrato', element: <ExtratoPage /> },
                  { path: 'cobrancas', element: <CobrancasPage /> },
                ],
              },
              { path: '/relatorios', element: <ReportsPage /> },
              {
                element: <RequireAdmin />,
                children: [{ path: '/configuracoes/usuarios', element: <UsersPage /> }],
              },
              { path: '*', element: <Navigate to="/" replace /> },
            ],
          },
        ],
      },
    ],
  },
])
