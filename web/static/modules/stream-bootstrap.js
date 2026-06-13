/**
 * Stream bootstrap for legacy globals.
 *
 * Keeps `window.StreamOrchestrator` only as compatibility glue.
 */
import { StreamOrchestrator } from './stream-orchestrator.js';

// window.StreamOrchestrator = StreamOrchestrator; // removed — no legacy callers
