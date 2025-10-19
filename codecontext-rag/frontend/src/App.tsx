// codecontext-rag/frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AppProvider } from './context/AppContext'
import { Layout } from './components/layout/Layout'

// Existing Pages
import { Dashboard } from './pages/Dashboard'
import { Repositories } from './pages/Repositories'
import { Search } from './pages/Search'
import { Recommendations } from './pages/Recommendations'
import { Dependencies } from './pages/Dependencies'
import { Graphs } from './pages/Graphs'
import { Context } from './pages/Context'
import { Prompts } from './pages/Prompts'
import { Patches } from './pages/Patches'
import { Features } from './pages/Features'
import { ProductAnalysis } from './pages/ProductAnalysis'
import { ImpactAnalysis } from './pages/ImpactAnalysis'
import { Tests } from './pages/Tests'

// New Pages
import { Orchestration } from './pages/Orchestration'
import { TaskAnalysis } from './pages/TaskAnalysis'
import { AgentFeedback } from './pages/AgentFeedback'
import { RunnerValidation } from './pages/RunnerValidation'

function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="repositories" element={<Repositories />} />
            <Route path="search" element={<Search />} />
            <Route path="recommendations" element={<Recommendations />} />
            <Route path="dependencies" element={<Dependencies />} />
            <Route path="graphs" element={<Graphs />} />
            <Route path="context" element={<Context />} />
            <Route path="prompts" element={<Prompts />} />
            <Route path="patches" element={<Patches />} />
            <Route path="features" element={<Features />} />
            <Route path="product-analysis" element={<ProductAnalysis />} />
            <Route path="impact" element={<ImpactAnalysis />} />
            <Route path="tests" element={<Tests />} />
            <Route path="orchestration" element={<Orchestration />} />
            <Route path="task-analysis" element={<TaskAnalysis />} />
            <Route path="agent-feedback" element={<AgentFeedback />} />
            <Route path="runner-validation" element={<RunnerValidation />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}

export default App