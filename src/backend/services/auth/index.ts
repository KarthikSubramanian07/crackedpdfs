/**
 * Clerk Authentication Utilities
 * 
 * Helper functions for authentication and authorization.
 */

import { auth, currentUser } from '@clerk/nextjs/server';

/**
 * Error thrown when a request lacks a valid Clerk session
 * or attempts to spoof a tenant identity.
 */
export class UnauthorizedError extends Error {
  constructor(message = 'Unauthorized') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

/**
 * Get current user's tenant ID (Clerk user ID)
 */
export async function getTenantId(): Promise<string> {
  const { userId } = await auth();
  
  if (!userId) {
    throw new Error('Unauthorized - no user ID found');
  }
  
  return userId;
}

/**
 * Get current user object
 */
export async function getCurrentUser() {
  const user = await currentUser();
  
  if (!user) {
    throw new Error('Unauthorized - no user found');
  }
  
  return user;
}

/**
 * Verify tenant access (for multi-tenant operations)
 */
export async function verifyTenantAccess(requestedTenantId: string): Promise<boolean> {
  const { userId } = await auth();
  
  if (!userId) {
    return false;
  }
  
  // In multi-tenant system, ensure user can only access their own data
  return userId === requestedTenantId;
}

/**
 * Extract tenant ID from request headers
 */
export function getTenantIdFromHeaders(headers: Headers): string {
  const tenantId = headers.get('x-tenant-id');
  
  if (!tenantId) {
    throw new Error('Missing x-tenant-id header');
  }
  
  return tenantId;
}

/**
 * Derive the current tenant strictly from Clerk and optionally
 * validate that any provided x-tenant-id header matches.
 */
export async function requireTenantContext(headers?: Headers): Promise<string> {
  const { userId } = await auth();

  if (!userId) {
    throw new UnauthorizedError('Unauthorized');
  }

  const headerTenantId = headers?.get('x-tenant-id');
  if (headerTenantId && headerTenantId !== userId) {
    console.warn('Tenant header mismatch', {
      headerTenantId,
      authenticatedTenantId: userId,
    });
    throw new UnauthorizedError('Tenant mismatch');
  }

  return userId;
}
