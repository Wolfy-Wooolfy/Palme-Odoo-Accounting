import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User } from 'lucide-react';
import clsx from 'clsx';
import ToolBadge from './ToolBadge';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={clsx('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div className={clsx(
        'flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center',
        isUser ? 'bg-primary-600' : 'bg-violet-600',
      )}>
        {isUser
          ? <User className="h-4 w-4 text-white" />
          : <Bot className="h-4 w-4 text-white" />
        }
      </div>

      <div className={clsx('flex flex-col gap-1.5 max-w-[75%]', isUser && 'items-end')}>
        {/* Tool badges */}
        {!isUser && message.tool_calls?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {message.tool_calls.map((tc, i) => (
              <ToolBadge key={i} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Bubble */}
        <div className={clsx(
          'rounded-2xl px-4 py-3 text-sm leading-relaxed',
          isUser
            ? 'bg-primary-600 text-white rounded-tr-sm'
            : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm',
        )}>
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc ms-4 mb-2 space-y-0.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal ms-4 mb-2 space-y-0.5">{children}</ol>,
                li: ({ children }) => <li className="text-sm">{children}</li>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                code: ({ inline, children }) =>
                  inline
                    ? <code className="bg-slate-100 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
                    : <pre className="bg-slate-100 rounded-lg p-3 text-xs font-mono overflow-x-auto mb-2"><code>{children}</code></pre>,
                table: ({ children }) => (
                  <div className="overflow-x-auto mb-2">
                    <table className="text-xs border-collapse w-full">{children}</table>
                  </div>
                ),
                th: ({ children }) => <th className="border border-slate-200 px-2 py-1 bg-slate-50 font-semibold text-start">{children}</th>,
                td: ({ children }) => <td className="border border-slate-200 px-2 py-1">{children}</td>,
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>
      </div>
    </div>
  );
}
