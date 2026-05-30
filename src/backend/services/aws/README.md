# AWS Services

Integration modules for AWS services used in the Solvance processing pipeline.

## 📦 Services

### S3 - File Storage
- Upload/download documents
- Presigned URLs for temporary access
- Multi-region replication (future)

### Lambda - Rust Processing
- Execute Rust watermarking functions
- Fast processing for files < 10MB
- Auto-scaling based on load

### ECS Fargate - Heavy Processing
- Process large files > 10MB
- Long-running jobs (> 15 minutes)
- Custom compute resources

### SQS - Job Queue
- Async job processing
- Retry logic for failed jobs
- Batch processing support

## 🔧 Configuration

Add to `.env`:

```bash
# AWS Credentials
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# S3 Configuration
AWS_S3_BUCKET=solvance-documents
AWS_S3_BUCKET_PROCESSED=solvance-protected

# Lambda Configuration
AWS_LAMBDA_FUNCTION=rust-document-processor

# ECS Configuration
AWS_ECS_CLUSTER=solvance-processing
AWS_ECS_TASK=rust-watermark-task
AWS_SUBNET_ID=subnet-xxx
AWS_SECURITY_GROUP_ID=sg-xxx

# SQS Configuration
AWS_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/processing-queue
```

## 🚀 Setup Instructions

### 1. Install AWS SDK

```bash
npm install @aws-sdk/client-s3 @aws-sdk/client-lambda @aws-sdk/client-ecs @aws-sdk/client-sqs
```

### 2. Deploy Rust Lambda

```bash
cd lambda/watermark
cargo lambda build --release --arm64
cargo lambda deploy --region us-east-1 rust-document-processor
```

### 3. Create S3 Buckets

```bash
aws s3 mb s3://solvance-documents --region us-east-1
aws s3 mb s3://solvance-protected --region us-east-1
```

### 4. Create SQS Queue

```bash
aws sqs create-queue --queue-name processing-queue --region us-east-1
```

### 5. Create ECS Cluster (Optional - for large files)

```bash
aws ecs create-cluster --cluster-name solvance-processing --region us-east-1
```

## 📊 Service Selection Logic

```typescript
import { selectProcessingService } from '@/backend/services/aws';

const service = selectProcessingService(fileSize, estimatedDuration);
// Returns 'lambda' or 'ecs' based on requirements
```

**Decision Matrix:**
- **File < 10MB, Time < 15min** → Lambda (fast, cheap)
- **File > 10MB, Time > 15min** → ECS (flexible, unlimited)

## 🔗 Integration with Processing Pipeline

```typescript
// Layer 02: Watermarking
import { LambdaService } from '@/backend/services/aws';

async function watermarkDocument(documentId, tenantId, data) {
  // Upload to S3
  const s3Key = await S3Service.upload(`${tenantId}/${documentId}.pdf`, data);
  
  // Invoke Rust Lambda
  const result = await LambdaService.invokeProcessor({
    documentId,
    tenantId,
    s3Key,
    stage: 'watermark',
    config: { strength: 0.8 }
  });
  
  // Download processed file
  return await S3Service.download(result.outputS3Key);
}
```

## 🛡️ Security

### IAM Policies

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::solvance-documents/*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": "arn:aws:lambda:us-east-1:*:function:rust-document-processor"
    }
  ]
}
```

### Environment Variables

**Never commit AWS credentials!** Use IAM roles in production:
- Lambda execution role for Lambda functions
- ECS task role for ECS tasks
- EC2 instance profile for servers

## 💰 Cost Optimization

### Lambda
- **Free tier**: 1M requests + 400,000 GB-seconds/month
- **After free tier**: $0.20 per 1M requests
- **Best for**: Small files, frequent processing

### ECS Fargate
- **Cost**: ~$0.04 per vCPU-hour + $0.004 per GB-hour
- **Best for**: Large files, batch processing

### S3
- **Storage**: $0.023 per GB/month
- **Requests**: $0.005 per 1,000 PUT requests
- **Best practice**: Use lifecycle policies to archive old files

## 📈 Monitoring

Use CloudWatch for monitoring:

```typescript
// Example: Track Lambda invocation metrics
import { CloudWatch } from '@aws-sdk/client-cloudwatch';

await cloudwatch.putMetricData({
  Namespace: 'Solvance/Processing',
  MetricData: [{
    MetricName: 'ProcessingTime',
    Value: processingTimeMs,
    Unit: 'Milliseconds',
    Dimensions: [
      { Name: 'Stage', Value: 'watermarking' },
      { Name: 'TenantId', Value: tenantId }
    ]
  }]
});
```

## 🔄 Current Status

**Implementation Status:**
- ✅ Service structure created
- ✅ Type definitions complete
- ⏳ S3 integration - **placeholder (implement when ready)**
- ⏳ Lambda integration - **placeholder (implement when ready)**
- ⏳ ECS integration - **placeholder (implement when ready)**
- ⏳ SQS integration - **placeholder (implement when ready)**

**Next Steps:**
1. Configure AWS credentials
2. Deploy Rust Lambda function
3. Implement S3 upload/download
4. Test end-to-end pipeline
