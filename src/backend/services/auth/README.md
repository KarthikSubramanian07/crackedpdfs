# Authentication Service (Clerk)

Utility functions for Clerk authentication and multi-tenant authorization.

## 🎯 Purpose

Provide reusable authentication helpers for API routes and server components.

## 🔐 Functions

### `getTenantId()`

Get the current authenticated user's ID (tenant ID for multi-tenancy):

```typescript
import { getTenantId } from '@/backend/services/auth';

// In API route
export async function GET() {
  const tenantId = await getTenantId();
  // Use tenantId for database queries
}
```

### `getCurrentUser()`

Get the full Clerk user object:

```typescript
import { getCurrentUser } from '@/backend/services/auth';

const user = await getCurrentUser();
console.log(user.emailAddresses[0].emailAddress);
console.log(user.firstName, user.lastName);
```

### `verifyTenantAccess()`

Verify a user has access to a specific tenant's data:

```typescript
import { verifyTenantAccess } from '@/backend/services/auth';

const hasAccess = await verifyTenantAccess(requestedTenantId);
if (!hasAccess) {
  return new Response('Forbidden', { status: 403 });
}
```

### `requireTenantContext()`

Derive the tenant straight from Clerk and reject spoofed headers:

```typescript
import { requireTenantContext } from '@/backend/services/auth';

export async function POST(request: Request) {
  const tenantId = await requireTenantContext(request.headers);
  // Use tenantId with full confidence it matches Clerk
}
```

### `getTenantIdFromHeaders()` (legacy / trusted services only)

Extract tenant ID from request headers (for API routes):

```typescript
import { getTenantIdFromHeaders } from '@/backend/services/auth';

export async function POST(request: Request) {
  const tenantId = getTenantIdFromHeaders(request.headers);
  // Use tenantId
}
```

> ⚠️ Only use this helper for trusted server-to-server automation (cron jobs, admin CLIs). Public routes must call `requireTenantContext()` instead of trusting headers.

## 🔧 Usage in API Routes

### Pattern 1: Server-Side Auth (Recommended)

```typescript
import { requireTenantContext, UnauthorizedError } from '@/backend/services/auth';
import { db } from '@/backend/db';
import { documents } from '@/backend/db/schema';
import { eq } from 'drizzle-orm';

export async function GET() {
  try {
    // Get tenant ID from Clerk session
    const tenantId = await requireTenantContext();
    
    // Query with tenant isolation
    const docs = await db.select()
      .from(documents)
      .where(eq(documents.tenantId, tenantId));
    
    return Response.json({ documents: docs });
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      return Response.json({ error: error.message }, { status: 401 });
    }
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }
}
```

## 🔒 Multi-Tenant Security

**CRITICAL**: Always enforce tenant isolation in queries:

```typescript
// ✅ Good - tenant isolated
const docs = await db.select()
  .from(documents)
  .where(eq(documents.tenantId, tenantId));

// ❌ Bad - exposes all tenants' data
const docs = await db.select()
  .from(documents);
```

## 🧪 Testing Auth

For development, you can bypass auth temporarily:

```typescript
// ONLY FOR DEVELOPMENT - NEVER IN PRODUCTION
const tenantId = process.env.NODE_ENV === 'development' 
  ? 'test-user-123' 
  : await getTenantId();
```

## 🔗 Clerk Configuration

Ensure these environment variables are set:

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxx
CLERK_SECRET_KEY=sk_test_xxx
```

## 📚 Related

- **Middleware**: `middleware.ts` - Protects routes
- **Frontend**: Use Clerk's `useUser()` hook in components
- **Backend**: Use these utilities in API routes

## 🚀 Future Enhancements

- **Role-based access control (RBAC)**: Admin vs. user roles
- **Organization support**: Multi-user teams
- **API key authentication**: For programmatic access
