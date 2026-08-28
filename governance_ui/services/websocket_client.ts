/**
 * WebSocket Client for Governance UI
 * Connects to the CCRO Orchestrator WebSocket for live state updates.
 */

const WS_BASE_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000/ws";

export interface ResilienceState {
  resilience_state: string;
  capacity_margin: number;
  thread_id: string;
}

export interface ApprovalCardData {
  plan_id: string;
  proposed_allocation: {
    assignments: Array<{
      site_id: string;
      allocated_units: number;
      vehicle_id: string;
      priority_score: number;
      payload_mass_kg: number;
    }>;
    dropped_sites: Array<{
      site_id: string;
      reason: string;
      priority_score: number;
    }>;
    objective_value: number;
  };
  policy_weights: {
    w1: number;
    w2: number;
    w3: number;
    cited_clauses: Array<{
      clause_id: string;
      source_doc: string;
      similarity_score: number;
      text_excerpt: string;
    }>;
    confidence_score: number;
  };
}

export class GovernanceWebSocket {
  private ws: WebSocket | null = null;
  private threadId: string;
  private onStateUpdate: (state: ResilienceState) => void;
  private onApprovalCard: (card: ApprovalCardData) => void;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;

  constructor(
    threadId: string,
    onStateUpdate: (state: ResilienceState) => void,
    onApprovalCard: (card: ApprovalCardData) => void
  ) {
    this.threadId = threadId;
    this.onStateUpdate = onStateUpdate;
    this.onApprovalCard = onApprovalCard;
  }

  connect() {
    const url = `${WS_BASE_URL}/${this.threadId}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log("WebSocket connected:", url);
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      switch (message.type) {
        case "state_update":
          this.onStateUpdate(message.data);
          break;
        case "approval_card":
          this.onApprovalCard(message.data);
          break;
        default:
          console.log("Unknown message type:", message.type);
      }
    };

    this.ws.onclose = () => {
      console.log("WebSocket disconnected");
      this.attemptReconnect();
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
      setTimeout(() => this.connect(), delay);
    }
  }

  sendApprovalDecision(decision: string, modifications?: any[]) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          type: "approval_decision",
          decision,
          modifications,
          thread_id: this.threadId,
        })
      );
    }
  }

  disconnect() {
    this.ws?.close();
  }
}
