# Payments Service (Stripe)

Stripe integration for subscription management and billing.

## 🎯 Purpose

Handle all payment-related operations including subscriptions, billing, and usage tracking.

## 🚧 Current Status

**Not yet implemented** - Placeholder for future Stripe integration.

## 📋 Planned Features

### Subscription Tiers

```typescript
const PLANS = {
  free: {
    name: 'Free',
    price: 0,
    documentsPerMonth: 10,
    features: ['Basic watermarking', 'Email support']
  },
  pro: {
    name: 'Professional',
    price: 29,
    documentsPerMonth: 500,
    features: ['Advanced watermarking', 'Encryption', 'Priority support']
  },
  enterprise: {
    name: 'Enterprise',
    price: 299,
    documentsPerMonth: 'unlimited',
    features: ['All features', 'Custom SLA', 'Dedicated support']
  }
};
```

### Stripe Integration

```typescript
// Future implementation
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

export async function createCheckoutSession(
  tenantId: string,
  priceId: string
): Promise<string> {
  const session = await stripe.checkout.sessions.create({
    customer_email: userEmail,
    mode: 'subscription',
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: `${process.env.NEXT_PUBLIC_URL}/dashboard?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${process.env.NEXT_PUBLIC_URL}/pricing`,
  });
  
  return session.url!;
}
```

### Usage Tracking

```typescript
// Track document processing for billing
export async function trackUsage(
  tenantId: string,
  documentsProcessed: number
): Promise<void> {
  // Update usage in Stripe
  await stripe.subscriptionItems.createUsageRecord(
    subscriptionItemId,
    { quantity: documentsProcessed }
  );
}
```

### Webhooks

```typescript
// Handle Stripe webhook events
export async function handleWebhook(event: Stripe.Event): Promise<void> {
  switch (event.type) {
    case 'customer.subscription.created':
      // Update user's subscription status
      break;
    case 'invoice.payment_succeeded':
      // Reset monthly document quota
      break;
    case 'customer.subscription.deleted':
      // Downgrade to free plan
      break;
  }
}
```

## 🔧 Environment Variables (Future)

```bash
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Price IDs from Stripe Dashboard
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_ENTERPRISE=price_xxx
```

## 🔗 Integration Points

### With Dashboard
- Display current subscription plan
- Show usage metrics (documents processed / limit)
- Upgrade/downgrade buttons

### With Processing Pipeline
- Check if user has available quota before processing
- Track each processed document for billing
- Block processing if quota exceeded

### With Database
- Store subscription status in `tenant_metrics` table
- Track monthly usage for metered billing

## 📚 Resources

- [Stripe Documentation](https://stripe.com/docs)
- [Next.js + Stripe Guide](https://vercel.com/guides/getting-started-with-nextjs-typescript-stripe)
- [Subscription Management Best Practices](https://stripe.com/docs/billing/subscriptions/overview)

## 🚀 Implementation Steps (Future)

1. **Setup Stripe Account**
   - Create products and prices in Stripe Dashboard
   - Get API keys

2. **Install Stripe SDK**
   ```bash
   npm install stripe @stripe/stripe-js
   ```

3. **Create Checkout Flow**
   - API route: `/api/stripe/checkout`
   - Success/cancel pages

4. **Setup Webhook Endpoint**
   - API route: `/api/stripe/webhook`
   - Verify webhook signatures

5. **Implement Usage Tracking**
   - Track in processing pipeline
   - Report to Stripe daily/monthly

6. **Add Billing Portal**
   - Allow users to manage subscriptions
   - Update payment methods

## 💡 Notes

This service is prepared for future implementation. The architecture is designed to integrate smoothly with the existing multi-tenant system and processing pipeline.
