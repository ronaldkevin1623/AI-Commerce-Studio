import { ThemeProvider, CssBaseline } from "@mui/material";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import theme from "./theme/theme";
import AppShell from "./components/shared/AppShell";
import { RoleProvider, useRole } from "./context/RoleContext";
import RequireRole from "./components/shared/RequireRole";
import { ConversationProvider } from "./context/ConversationContext";
import { HiveSettingsProvider } from "./context/HiveSettingsContext";
import { CartProvider } from "./context/CartContext";

import LandingPage from "./pages/LandingPage";
import HiveMindPage from "./pages/HiveMindPage";
import AgentConsolePage from "./pages/AgentConsolePage";
import MerchantPage from "./pages/MerchantPage";
import MerchantProductsPage from "./pages/MerchantProductsPage";
import MerchantProductFormPage from "./pages/MerchantProductFormPage";
import MerchantConsolePage from "./pages/MerchantConsolePage";
import MerchantGrowthPage from "./pages/MerchantGrowthPage";
import MerchantGrowthAgentsPage from "./pages/MerchantGrowthAgentsPage";
import MerchantGrowthCampaignsPage from "./pages/MerchantGrowthCampaignsPage";
import MerchantGrowthAttributionPage from "./pages/MerchantGrowthAttributionPage";
import MerchantGrowthRelationshipsPage from "./pages/MerchantGrowthRelationshipsPage";
import MerchantOrdersPage from "./pages/MerchantOrdersPage";
import RedTeamPage from "./pages/RedTeamPage";
import SecurityPage from "./pages/SecurityPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import OrdersPage from "./pages/OrdersPage";
import TripsPage from "./pages/TripsPage";
import TripDetailPage from "./pages/TripDetailPage";
import OrderTrackingPage from "./pages/OrderTrackingPage";
import AuditTrailPage from "./pages/AuditTrailPage";
import FailureRecoveryPage from "./pages/FailureRecoveryPage";

/**
 * HOME IS A DIFFERENT AGENT DEPENDING ON WHICH SIDE YOU ARE ON.
 *
 * Both parties get a conversational agent at `/console`, and they are not
 * the same agent: the buyer's turns a sentence into a transaction, the
 * merchant's turns a sentence into an analysis of their own shop. One route
 * rather than two because "Home" should mean the same thing to both — the
 * place you talk to your agent — and because the role switcher in the top
 * bar then swaps the whole workbench in one click, which is the demo.
 */
function RoleConsole() {
  const { role } = useRole();
  return role === "merchant" ? <MerchantConsolePage /> : <AgentConsolePage />;
}

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
            <Route path="/console" element={<RoleConsole />} />
            <Route path="/approvals" element={<ApprovalsPage />} />
            <Route path="/merchant" element={<MerchantPage />} />
            <Route path="/merchant/products" element={<MerchantProductsPage />} />
            <Route path="/merchant/products/new" element={<MerchantProductFormPage />} />
            <Route path="/merchant/growth" element={<MerchantGrowthPage />} />
            <Route path="/merchant/growth/agents" element={<MerchantGrowthAgentsPage />} />
            <Route path="/merchant/growth/campaigns" element={<MerchantGrowthCampaignsPage />} />
            <Route path="/merchant/growth/attribution" element={<MerchantGrowthAttributionPage />} />
            <Route path="/merchant/growth/relationships" element={<MerchantGrowthRelationshipsPage />} />
            <Route path="/merchant/orders" element={<MerchantOrdersPage />} />
            <Route path="/trips" element={<TripsPage />} />
            <Route path="/trips/:tripId" element={<TripDetailPage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/orders/:orderId" element={<OrderTrackingPage />} />
            <Route path="/audit" element={<AuditTrailPage />} />
            <Route path="/recovery" element={<FailureRecoveryPage />} />
            <Route path="/redteam" element={<RedTeamPage />} />
            <Route path="/security" element={<SecurityPage />} />
            {/* The store hive was folded into the main hive, which already
                carries every shop node it showed. Redirected rather than
                dropped: an old link or a bookmark otherwise lands on the
                shell with an empty pane, which reads as a broken build. */}
            <Route path="/merchant/hive" element={<Navigate to="/hive" replace />} />
            {/* Anything unrecognised goes home for the same reason. */}
            <Route path="*" element={<Navigate to="/console" replace />} />
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