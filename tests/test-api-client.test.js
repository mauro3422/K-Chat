import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import './setup.js';
import { ApiClient } from '../web/static/modules/api-client.js';

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('ApiClient', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  describe('chatStream', () => {
    it('calls /chat/{session_id} with POST', () => {
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.chatStream('session-1', 'hello', 'model-x', new AbortController());
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/chat/session-1?model=model-x',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'hello' }),
        })
      );
    });

    it('passes the abort controller signal', () => {
      const controller = new AbortController();
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.chatStream('s1', 'hi', 'm1', controller);
      
      expect(mockFetch.mock.calls[0][1].signal).toBe(controller.signal);
    });
  });

  describe('sidebar', () => {
    it('returns HTML text from sidebar endpoint', async () => {
      mockFetch.mockResolvedValue(new Response('<div>sidebar</div>'));
      const result = await ApiClient.sidebar();
      
      expect(result).toBe('<div>sidebar</div>');
      expect(mockFetch).toHaveBeenCalledWith('/sidebar?current=null');
    });
  });

  describe('loadMessages', () => {
    it('calls /sessions/{id}/messages', () => {
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.loadMessages('session-1');
      expect(mockFetch).toHaveBeenCalledWith('/sessions/session-1/messages');
    });
  });

  describe('renameSession', () => {
    it('POSTs to /sessions/{id}/rename', () => {
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.renameSession('s1', 'New Name');
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/sessions/s1/rename',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'New Name' }),
        })
      );
    });
  });

  describe('deleteSession', () => {
    it('POSTs to /sessions/{id}/delete', () => {
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.deleteSession('s1');
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/sessions/s1/delete',
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  describe('saveWidgetState', () => {
    it('POSTs widget state to the correct endpoint', () => {
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.saveWidgetState('s1', 'widget-key', { code: 'hi' });
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/sessions/s1/widgets/widget-key/state',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: { code: 'hi' } }),
        })
      );
    });
  });

  describe('loadWidgetStates', () => {
    it('GETs widget states for a session', () => {
      mockFetch.mockResolvedValue(new Response('[]'));
      ApiClient.loadWidgetStates('s1');
      expect(mockFetch).toHaveBeenCalledWith('/sessions/s1/widgets/states');
    });
  });

  describe('loadDebugInfo', () => {
    it('GETs debug info for a session', () => {
      mockFetch.mockResolvedValue(new Response('{}'));
      ApiClient.loadDebugInfo('s1');
      expect(mockFetch).toHaveBeenCalledWith('/sessions/s1/debug');
    });
  });

  describe('loadBackendLogs', () => {
    it('GETs backend logs', () => {
      mockFetch.mockResolvedValue(new Response('[]'));
      ApiClient.loadBackendLogs();
      expect(mockFetch).toHaveBeenCalledWith('/debug/backend-logs');
    });
  });

  describe('sendClientLogs', () => {
    it('POSTs log entries to /api/logs/client', () => {
      mockFetch.mockResolvedValue(new Response('ok'));
      ApiClient.sendClientLogs([{ level: 'error', msg: 'test' }]);
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/logs/client',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify([{ level: 'error', msg: 'test' }]),
        })
      );
    });
  });

  describe('transcribeAudio', () => {
    it('POSTs FormData to /api/asr/transcribe', () => {
      mockFetch.mockResolvedValue(new Response('{"text":"hello"}'));
      const blob = new Blob(['audio data'], { type: 'audio/webm' });
      ApiClient.transcribeAudio(blob);
      
      const call = mockFetch.mock.calls[0];
      expect(call[0]).toBe('/api/asr/transcribe');
      expect(call[1].method).toBe('POST');
      expect(call[1].body).toBeInstanceOf(FormData);
    });
  });

  describe('network error handling', () => {
    it('propagates network errors', async () => {
      mockFetch.mockRejectedValue(new Error('Network failure'));
      
      await expect(ApiClient.loadMessages('s1')).rejects.toThrow('Network failure');
    });

    it('propagates HTTP errors as response objects', async () => {
      mockFetch.mockResolvedValue(new Response('Not Found', { status: 404 }));
      
      const res = await ApiClient.loadMessages('s1');
      expect(res.status).toBe(404);
    });
  });
});
