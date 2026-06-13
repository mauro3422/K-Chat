/**
 * Chat form bootstrap for legacy globals.
 *
 * Keeps `window.KairosForm` only as compatibility glue.
 */
import { KairosForm } from './chat-form.js';

// window.KairosForm = KairosForm; // removed — no legacy callers
