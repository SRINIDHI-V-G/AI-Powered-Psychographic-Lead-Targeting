import axios from 'axios';
import type { DemoSetupResponse } from '../types/api';

// Read the demo secret from the build-time public env var.
// Set NEXT_PUBLIC_DEMO_SECRET in .env.local for development only.
// In production this var must be absent (demo is disabled server-side).
const DEMO_SECRET = process.env.NEXT_PUBLIC_DEMO_SECRET ?? '';

function demoHeaders() {
  return DEMO_SECRET ? { 'X-Demo-Secret': DEMO_SECRET } : {};
}

export async function setupDemo(): Promise<DemoSetupResponse> {
  const { data } = await axios.post<DemoSetupResponse>(
    '/api/v1/demo/setup',
    {},
    { headers: demoHeaders() },
  );
  return data;
}

export async function getDemoUsers(productId: string) {
  const { data } = await axios.get(`/api/v1/demo/${productId}/users`, {
    headers: demoHeaders(),
  });
  return data;
}

export async function getDemoLeads(productId: string) {
  const { data } = await axios.get(`/api/v1/demo/${productId}/leads`, {
    headers: demoHeaders(),
  });
  return data;
}
