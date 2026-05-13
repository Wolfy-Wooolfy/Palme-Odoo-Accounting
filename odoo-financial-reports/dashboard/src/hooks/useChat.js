import { useMutation, useQuery } from '@tanstack/react-query';
import { sendChat, getChatStatus } from '../api/chat';

export function useChatStatus() {
  return useQuery({
    queryKey: ['chat-status'],
    queryFn: getChatStatus,
    staleTime: 60_000,
    retry: false,
  });
}

export function useChatMutation() {
  return useMutation({
    mutationFn: sendChat,
  });
}
