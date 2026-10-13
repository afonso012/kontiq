import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './styles/tokens.css'
import './styles/componentes.css'
import './styles/app.css'
import ConfirmarEmail from './pages/ConfirmarEmail'
import Entrar from './pages/Entrar'
import PortalInicio from './pages/PortalInicio'
import Painel from './pages/Painel'
import EmpresaFaturas from './pages/EmpresaFaturas'
import ConferirFatura from './pages/ConferirFatura'
import Exportacoes from './pages/Exportacoes'
import Equipa from './pages/Equipa'
import Convite from './pages/Convite'
import Portal from './pages/Portal'
import Recuperar from './pages/Recuperar'
import Registo from './pages/Registo'
import { destino, Exige, SessaoProvider, SoSemSessao, useSessao } from './sessao'

function Raiz() {
  const { eu, carregado } = useSessao()
  return carregado ? <Navigate to={destino(eu)} replace /> : <div className="carregar" aria-busy="true" />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SessaoProvider>
        <Routes>
          <Route path="/" element={<Raiz />} />
          <Route path="/entrar" element={<SoSemSessao permitir="portal"><Entrar /></SoSemSessao>} />
          <Route path="/registo" element={<SoSemSessao><Registo /></SoSemSessao>} />
          <Route path="/recuperar" element={<SoSemSessao><Recuperar /></SoSemSessao>} />
          <Route path="/portal" element={<SoSemSessao permitir="gabinete"><Portal /></SoSemSessao>} />
          <Route path="/confirmar-email" element={<Exige tipo="gabinete-por-confirmar"><ConfirmarEmail /></Exige>} />
          <Route path="/painel" element={<Exige tipo="gabinete"><Painel /></Exige>} />
          <Route path="/empresas/:id" element={<Exige tipo="gabinete"><EmpresaFaturas /></Exige>} />
          <Route path="/faturas/:id" element={<Exige tipo="gabinete"><ConferirFatura /></Exige>} />
          <Route path="/exportacoes" element={<Exige tipo="gabinete"><Exportacoes /></Exige>} />
          <Route path="/equipa" element={<Exige tipo="gabinete"><Equipa /></Exige>} />
          <Route path="/convite/:token" element={<Convite />} />
          <Route path="/portal/inicio" element={<Exige tipo="portal"><PortalInicio /></Exige>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </SessaoProvider>
    </BrowserRouter>
  </StrictMode>,
)
