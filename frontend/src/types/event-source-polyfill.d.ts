// Type declarations for event-source-polyfill
declare module "event-source-polyfill" {
  export interface EventSourcePolyfillInit {
    headers?: Record<string, string>;
    withCredentials?: boolean;
    https?: { rejectUnauthorized?: boolean };
    heartbeatTimeout?: number;
  }

  export class EventSourcePolyfill extends EventTarget {
    constructor(url: string, init?: EventSourcePolyfillInit);
    readonly url: string;
    readonly readyState: number;
    readonly CONNECTING: 0;
    readonly OPEN: 1;
    readonly CLOSED: 2;
    onopen: ((event: MessageEvent) => void) | null;
    onmessage: ((event: MessageEvent) => void) | null;
    onerror: ((event: Event) => void) | null;
    close(): void;
  }

  export default EventSourcePolyfill;
}
