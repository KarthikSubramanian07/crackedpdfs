import { db } from '@/db';
import { accessibilityRequests } from '@/db/schema';

async function main() {
    const now = new Date();
    
    // Helper function to create dates relative to now
    const daysAgo = (days: number) => {
        const date = new Date(now);
        date.setDate(date.getDate() - days);
        return date.toISOString();
    };
    
    // Helper function to add duration to a date
    const addDuration = (dateStr: string, duration: string) => {
        const date = new Date(dateStr);
        switch(duration) {
            case '24h':
                date.setHours(date.getHours() + 24);
                break;
            case '1w':
                date.setDate(date.getDate() + 7);
                break;
            case '1m':
                date.setDate(date.getDate() + 30);
                break;
        }
        return date.toISOString();
    };
    
    const sampleAccessibilityRequests = [
        // PENDING Request 1
        {
            tenantId: 'tenant-demo',
            documentId: 7,
            studentName: 'Sarah Chen',
            studentEmail: 'sarah.chen@berkeley.edu',
            reason: 'Extended time accommodation - need additional time due to ADHD diagnosis per DSP letter',
            dspLetterUrl: '/storage/dsp-letters/dsp-20241234.pdf',
            status: 'PENDING',
            expiryDuration: null,
            expiryDate: null,
            accessUrl: null,
            accessSentAt: null,
            createdAt: daysAgo(2),
            approvedAt: null,
            approvedBy: null,
        },
        
        // PENDING Request 2
        {
            tenantId: 'tenant-demo',
            documentId: 9,
            studentName: 'Marcus Washington',
            studentEmail: 'marcus.washington@berkeley.edu',
            reason: 'Visual impairment - require digital copy for screen reader accessibility',
            dspLetterUrl: '/storage/dsp-letters/dsp-20245678.pdf',
            status: 'PENDING',
            expiryDuration: null,
            expiryDate: null,
            accessUrl: null,
            accessSentAt: null,
            createdAt: daysAgo(1),
            approvedAt: null,
            approvedBy: null,
        },
        
        // APPROVED Request 1 (with 1 week expiry)
        {
            tenantId: 'tenant-demo',
            documentId: 8,
            studentName: 'Priya Patel',
            studentEmail: 'priya.patel@berkeley.edu',
            reason: 'Learning disability - need accessible format for note-taking accommodations',
            dspLetterUrl: '/storage/dsp-letters/dsp-20249012.pdf',
            status: 'APPROVED',
            expiryDuration: '1w',
            expiryDate: addDuration(daysAgo(7), '1w'),
            accessUrl: '/api/files/8/access?token=a3f8e9b2c1d4567890abcdef1234567890abcdef1234567890abcdef12345678',
            accessSentAt: daysAgo(7),
            createdAt: daysAgo(10),
            approvedAt: daysAgo(7),
            approvedBy: 101,
        },
        
        // APPROVED Request 2 (with 24 hour expiry)
        {
            tenantId: 'tenant-demo',
            documentId: 7,
            studentName: 'David Kim',
            studentEmail: 'david.kim@berkeley.edu',
            reason: 'Chronic pain condition - difficulty attending in-person exam, need remote access',
            dspLetterUrl: '/storage/dsp-letters/dsp-20243456.pdf',
            status: 'APPROVED',
            expiryDuration: '24h',
            expiryDate: addDuration(daysAgo(4), '24h'),
            accessUrl: '/api/files/7/access?token=9f2e7c8b5a6d4321098765fedcba4321098765fedcba4321098765fedcba4321',
            accessSentAt: daysAgo(4),
            createdAt: daysAgo(6),
            approvedAt: daysAgo(4),
            approvedBy: 102,
        },
        
        // DENIED Request
        {
            tenantId: 'tenant-demo',
            documentId: 9,
            studentName: 'Emily Rodriguez',
            studentEmail: 'emily.rodriguez@berkeley.edu',
            reason: 'Anxiety disorder - reduced distraction testing environment approved by DSP',
            dspLetterUrl: null,
            status: 'DENIED',
            expiryDuration: null,
            expiryDate: null,
            accessUrl: null,
            accessSentAt: null,
            createdAt: daysAgo(12),
            approvedAt: daysAgo(11),
            approvedBy: 103,
        },
    ];

    await db.insert(accessibilityRequests).values(sampleAccessibilityRequests);
    
    console.log('✅ Accessibility requests seeder completed successfully');
}

main().catch((error) => {
    console.error('❌ Seeder failed:', error);
});