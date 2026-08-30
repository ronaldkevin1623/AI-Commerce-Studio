import { ThemeProvider, CssBaseline } from "@mui/material";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import theme from "./theme/theme";
import AppShell from "./components/shared/AppShell";
import { ConversationProvider } from "./context/ConversationContext";
import { HiveSettingsProvider } from "./context/HiveSettingsContext";
import { CartProvider } from "./context/CartContext";
import { RoleProvider } from "./context/RoleContext";
import RequireRole from "./components/shared/RequireRole";

import LandingPage from "./pages/LandingPage";
import HiveMindPage from "./pages/HiveMindPage";
import AgentConsolePage from "./pages/AgentConsolePage";
import MerchantPage from "./pages/MerchantPage";
import MerchantProductsPage from "./pages/MerchantProductsPage";
import MerchantProductFormPage from "./pages/MerchantProductFormPage";
import MerchantGrowthPage from "./pages/MerchantGrowthPage";
import MerchantHivePage from "./pages/MerchantHivePage";
import MerchantOrdersPage from "./pages/MerchantOrdersPage";
import RedTeamPage from "./pages/RedTeamPage";
import SecurityPage from "./pages/SecurityPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import OrdersPage from "./pages/OrdersPage";
import OrderTrackingPage from "./pages/OrderTrackingPage";
import AuditTrailPage from "./pages/AuditTrailPage";
import FailureRecoveryPage from "./pages/FailureRecoveryPage";

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <RoleProvider>
        <ConversationProvider>
        <HiveSettingsProvider>
        <CartProvider>
        <AppShell>
          <RequireRole>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/hive" element={<HiveMindPage />} />
            <Route path="/console" element={<AgentConsolePage />} />
            <Route path="/approvals" element={<ApprovalsPage />} />
            <Route path="/merchant" element={<MerchantPage />} />
            <Route path="/merchant/products" element={<MerchantProductsPage />} />
            <Route path="/merchant/products/new" element={<MerchantProductFormPage />} />
            <Route path="/merchant/growth" element={<MerchantGrowthPage />} />
            <Route path="/merchant/hive" element={<MerchantHivePage />} />
            <Route path="/merchant/orders" element={<MerchantOrdersPage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/orders/:orderId" element={<OrderTrackingPage />} />
            <Route path="/audit" element={<AuditTrailPage />} />
            <Route path="/recovery" element={<FailureRecoveryPage />} />
            <Route path="/redteam" element={<RedTeamPage />} />
            <Route path="/security" element={<SecurityPage />} />
          </Routes>
          </RequireRole>
        </AppShell>
        </CartProvider>
        </HiveSettingsProvider>
        </ConversationProvider>
        </RoleProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}