import { proxyRequest, optionsResponse } from '@/app/api/zai-proxy/_lib';
import { NextRequest } from 'next/server';

export async function POST(request: NextRequest) {
  return proxyRequest('images/generations', request);
}

export async function OPTIONS() { return optionsResponse(); }
