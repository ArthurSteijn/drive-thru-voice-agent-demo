import { test, expect } from '@playwright/test';

test.describe('FastAPI Backend Integration', () => {

  test('should fetch health status from FastAPI backend', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:8000/health');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.status).toBe('ok');
  });

  test('should fetch menu from backend API endpoint', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:8000/api/menu');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(Array.isArray(data.items)).toBeTruthy();
  });

});
