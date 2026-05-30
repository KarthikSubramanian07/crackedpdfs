import { db } from '@/db';
import { documents } from '@/db/schema';
import crypto from 'crypto';

async function main() {
    const now = new Date();
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    
    const getRandomDate = (start: Date, end: Date) => {
        return new Date(start.getTime() + Math.random() * (end.getTime() - start.getTime()));
    };
    
    const generateAccessToken = () => {
        return crypto.randomBytes(32).toString('hex');
    };
    
    const sampleDocuments = [
        {
            tenantId: 'tenant-demo',
            filename: 'midterm-exam-cs101.pdf',
            originalFilename: 'midterm-exam-cs101.pdf',
            filePath: 'tenant-demo/documents/midterm-exam-cs101.pdf',
            fileSize: 2458000,
            fileType: 'application/pdf',
            status: 'completed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: JSON.stringify({
                pages: 12,
                textExtracted: true,
                ocrCompleted: true,
                processingTime: 45.3,
                confidence: 0.95
            })
        },
        {
            tenantId: 'tenant-demo',
            filename: 'final-project-guidelines.pdf',
            originalFilename: 'final-project-guidelines.pdf',
            filePath: 'tenant-demo/documents/final-project-guidelines.pdf',
            fileSize: 1876500,
            fileType: 'application/pdf',
            status: 'completed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: JSON.stringify({
                pages: 8,
                textExtracted: true,
                ocrCompleted: true,
                processingTime: 32.7,
                confidence: 0.98
            })
        },
        {
            tenantId: 'tenant-demo',
            filename: 'lecture-notes-week5.pdf',
            originalFilename: 'lecture-notes-week5.pdf',
            filePath: 'tenant-demo/documents/lecture-notes-week5.pdf',
            fileSize: 3245000,
            fileType: 'application/pdf',
            status: 'completed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: JSON.stringify({
                pages: 15,
                textExtracted: true,
                ocrCompleted: true,
                processingTime: 58.9,
                confidence: 0.92
            })
        },
        {
            tenantId: 'tenant-demo',
            filename: 'assignment-3-rubric.pdf',
            originalFilename: 'assignment-3-rubric.pdf',
            filePath: 'tenant-demo/documents/assignment-3-rubric.pdf',
            fileSize: 987500,
            fileType: 'application/pdf',
            status: 'completed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: JSON.stringify({
                pages: 5,
                textExtracted: true,
                ocrCompleted: true,
                processingTime: 21.4,
                confidence: 0.97
            })
        },
        {
            tenantId: 'tenant-demo',
            filename: 'syllabus-fall2024.pdf',
            originalFilename: 'syllabus-fall2024.pdf',
            filePath: 'tenant-demo/documents/syllabus-fall2024.pdf',
            fileSize: 1456000,
            fileType: 'application/pdf',
            status: 'completed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: JSON.stringify({
                pages: 10,
                textExtracted: true,
                ocrCompleted: true,
                processingTime: 38.6,
                confidence: 0.96
            })
        },
        {
            tenantId: 'tenant-demo',
            filename: 'chapter-7-summary.pdf',
            originalFilename: 'chapter-7-summary.pdf',
            filePath: 'tenant-demo/documents/chapter-7-summary.pdf',
            fileSize: 2134000,
            fileType: 'application/pdf',
            status: 'completed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: JSON.stringify({
                pages: 9,
                textExtracted: true,
                ocrCompleted: true,
                processingTime: 41.2,
                confidence: 0.94
            })
        },
        {
            tenantId: 'tenant-demo',
            filename: 'lab-manual-physics201.pdf',
            originalFilename: 'lab-manual-physics201.pdf',
            filePath: 'tenant-demo/documents/lab-manual-physics201.pdf',
            fileSize: 4567000,
            fileType: 'application/pdf',
            status: 'processing',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: null,
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: null
        },
        {
            tenantId: 'tenant-demo',
            filename: 'study-guide-final.pdf',
            originalFilename: 'study-guide-final.pdf',
            filePath: 'tenant-demo/documents/study-guide-final.pdf',
            fileSize: 3089000,
            fileType: 'application/pdf',
            status: 'processing',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: null,
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: null,
            metadata: null
        },
        {
            tenantId: 'tenant-demo',
            filename: 'research-paper-template.pdf',
            originalFilename: 'research-paper-template.pdf',
            filePath: 'tenant-demo/documents/research-paper-template.pdf',
            fileSize: 678000,
            fileType: 'application/pdf',
            status: 'queued',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: null,
            processingStartedAt: null,
            errorMessage: null,
            metadata: null
        },
        {
            tenantId: 'tenant-demo',
            filename: 'scanned-textbook-chapter.pdf',
            originalFilename: 'scanned-textbook-chapter.pdf',
            filePath: 'tenant-demo/documents/scanned-textbook-chapter.pdf',
            fileSize: 4987000,
            fileType: 'application/pdf',
            status: 'failed',
            accessToken: generateAccessToken(),
            uploadedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            processingStartedAt: getRandomDate(thirtyDaysAgo, now).toISOString(),
            errorMessage: 'OCR processing timeout',
            metadata: null
        }
    ];

    await db.insert(documents).values(sampleDocuments);
    
    console.log('✅ Documents seeder completed successfully');
}

main().catch((error) => {
    console.error('❌ Seeder failed:', error);
});