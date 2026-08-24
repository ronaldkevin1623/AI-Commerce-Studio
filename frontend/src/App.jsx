import { ThemeProvider, CssBaseline } from "@mui/material";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import theme from "./theme/theme";
import AppShell from "./components/shared/AppShell";

import LandingPage from "./pages/LandingPage";
import AgentConsolePage from "./pages/AgentConsolePage";
import AuditTrailPage from "./pages/AuditTrailPage";
import FailureRecoveryPage from "./pages/FailureRecoveryPage";

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/console" element={<AgentConsolePage />} />
            <Route path="/audit" element={<AuditTrailPage />} />
            <Route path="/recovery" element={<FailureRecoveryPage />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </ThemeProvider>
  );
}