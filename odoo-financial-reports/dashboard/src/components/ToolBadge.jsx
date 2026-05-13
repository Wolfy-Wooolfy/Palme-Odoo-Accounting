import { Wrench } from 'lucide-react';

const TOOL_LABELS = {
  get_trial_balance: 'Trial Balance',
  get_profit_loss: 'P&L',
  get_balance_sheet: 'Balance Sheet',
  get_general_ledger: 'General Ledger',
  get_customer_aging: 'Customer Aging',
  get_vendor_aging: 'Vendor Aging',
  get_cash_bank: 'Cash & Bank',
  get_sales: 'Sales',
  get_purchases: 'Purchases',
  get_diagnostics: 'Diagnostics',
  get_companies: 'Companies',
  search_accounts: 'Accounts Search',
};

export default function ToolBadge({ toolCall }) {
  const label = TOOL_LABELS[toolCall.name] ?? toolCall.name;

  return (
    <span className="inline-flex items-center gap-1.5 bg-violet-50 border border-violet-200 text-violet-700 rounded-full px-2.5 py-0.5 text-xs font-medium">
      <Wrench className="h-3 w-3 flex-shrink-0" />
      <span>{label}</span>
      {toolCall.result_summary && (
        <span className="text-violet-500 font-normal">· {toolCall.result_summary}</span>
      )}
    </span>
  );
}
