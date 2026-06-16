import { IEventBus } from '../../types/events';
import { IDebugApi } from '../../types/api';
import { IDebugManager } from '../../types/debug';
import { Logger, ILogger } from './Logger';

const instances = new Map<string, ILogger>();

export function getLogger(
  name: string,
  eventBus?: IEventBus,
  apiClient?: IDebugApi,
  debugManager?: IDebugManager,
): ILogger {
  if (!instances.has(name)) {
    instances.set(name, new Logger(name, eventBus, apiClient, debugManager));
  }
  return instances.get(name)!;
}
