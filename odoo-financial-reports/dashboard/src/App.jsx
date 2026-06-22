import { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import { FilterProvider } from './context/FilterContext';
import LoadingSpinner from './components/LoadingSpinner';

const Overview = lazy(() => import('./pages/Overview'));
const TrialBalance = lazy(() => import('./pages/TrialBalance'));
const ProfitLoss = lazy(() => import('./pages/ProfitLoss'));
const BalanceSheet = lazy(() => import('./pages/BalanceSheet'));
const Diagnostics = lazy(() => import('./pages/Diagnostics'));
const CustomerAging = lazy(() => import('./pages/CustomerAging'));
const VendorAging = lazy(() => import('./pages/VendorAging'));
const CashBank = lazy(() => import('./pages/CashBank'));
const GeneralLedger = lazy(() => import('./pages/GeneralLedger'));
const SalesReport = lazy(() => import('./pages/SalesReport'));
const PurchaseReport = lazy(() => import('./pages/PurchaseReport'));
const PosSessions = lazy(() => import('./pages/PosSessions'));
const Settings = lazy(() => import('./pages/Settings'));
const AIChat = lazy(() => import('./pages/AIChat'));

const PageFallback = () => (
  <div className="flex items-center justify-center h-64">
    <LoadingSpinner size="lg" />
  </div>
);

export default function App() {
  return (
    <FilterProvider>
      <Layout>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/trial-balance" element={<TrialBalance />} />
            <Route path="/profit-loss" element={<ProfitLoss />} />
            <Route path="/balance-sheet" element={<BalanceSheet />} />
            <Route path="/diagnostics" element={<Diagnostics />} />
            <Route path="/customer-aging" element={<CustomerAging />} />
            <Route path="/vendor-aging" element={<VendorAging />} />
            <Route path="/cash-bank" element={<CashBank />} />
            <Route path="/general-ledger" element={<GeneralLedger />} />
            <Route path="/sales" element={<SalesReport />} />
            <Route path="/purchases" element={<PurchaseReport />} />
            <Route path="/pos-sessions" element={<PosSessions />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/chat" element={<AIChat />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </FilterProvider>
  );
}
