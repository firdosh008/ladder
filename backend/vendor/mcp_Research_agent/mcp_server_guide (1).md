# Complete MCP Server Framework Guide

> **The Ultimate Guide to Building Production-Ready MCP Servers**
> 
> Based on our production MCP servers (Gmail, Apollo, Slack, QuickBooks, DocuSign, etc.) using direct JSON-RPC 2.0 implementation without external MCP SDK dependencies.

## Table of Contents

- [Framework Overview](#framework-overview)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Step-by-Step Implementation](#step-by-step-implementation)
  - [Step 1: Project Setup](#step-1-project-setup)
  - [Step 2: Environment Configuration (envs.ts)](#step-2-environment-configuration-envsts)
  - [Step 3: Main Server (index.ts)](#step-3-main-server-indexts)
  - [Step 4: Auth Routes (auth.routes.ts)](#step-4-auth-routes-authroutests)
  - [Step 5: Security Middleware](#step-5-security-middleware)
  - [Step 6: Tool Definitions](#step-6-tool-definitions)
  - [Step 7: API Service Layer](#step-7-api-service-layer)
- [Authentication & Bearer Token Handling](#authentication--bearer-token-handling)
- [Pre-OAuth Actions](#pre-oauth-actions)
- [Post-OAuth Actions & contextData](#post-oauth-actions--contextdata)
- [Integration Hub Compatibility](#integration-hub-compatibility)
- [Tool Schema Design](#tool-schema-design)
- [Testing & Validation](#testing--validation)
- [Deployment & Production](#deployment--production)
- [Cursor AI Prompt](#cursor-ai-prompt)

---

## Framework Overview

### What We Use

- **Direct JSON-RPC 2.0**: Simple HTTP endpoint handling MCP protocol methods directly - no external SDK needed
- **HTTP-Only Architecture**: Express.js with standard HTTP (no WebSocket complexity)
- **Single Port Design**: All endpoints on one HTTP server
- **Singleton Multi-Tenant**: One server instance serves unlimited tenants via bearer tokens (injected internally)
- **Integration Hub Ready**: OAuth credentials, metadata, post-auth, and pre-oauth endpoints
- **Security Hardened**: Protected auth endpoints with API key authentication
- **Stateless Design**: Simple "request, execute, respond" pattern
- **Centralized Config**: All environment variables managed in `src/config/envs.ts`

### What We Don't Use

- **No `@modelcontextprotocol/sdk`**: We implement JSON-RPC 2.0 directly - simpler, fewer dependencies, full control
- **No `bearerToken` in tool schemas**: Authentication is handled internally by the Integration Hub and injected into tool arguments at runtime - tools should NOT define bearerToken in their inputSchema
- **No WebSocket Complexity**: Persistent connections and connection management
- **No Multiple Ports**: Separate ports for different services
- **No Vendor SDKs**: Direct HTTP API clients via axios instead of flaky SDKs
- **No McpServer/StreamableHTTPServerTransport**: These are unnecessary when handling JSON-RPC directly

---

## Architecture

### Core Architecture Diagram

```
Client (Integration Hub / LLM)
    │ JSON-RPC 2.0 (HTTP POST)
    ▼
Express.js HTTP Server (Single Port)
    ├── POST /mcp           → MCP protocol handler (tools/list, tools/call, initialize)
    ├── GET  /auth/credentials/:id  → OAuth credentials (protected)
    ├── GET  /auth/metadata/:id     → Integration metadata (protected)
    ├── POST /auth/post-auth        → Post-OAuth processing (protected)
    ├── GET  /auth/status           → Auth health check (protected)
    ├── GET  /health                → Server health check
    └── GET  /assets/*              → Static brand assets
    │
    ▼
Tool Handlers (direct function calls)
    │
    ▼
API Service Layer (axios HTTP client)
    │
    ▼
Third Party API (Gmail, Slack, QuickBooks, etc.)
```

### Multi-Tenant Flow

```
Tenant A (bearerToken injected by Integration Hub) ──┐
Tenant B (bearerToken injected by Integration Hub) ──┤──► Single MCP Server ──► API calls with tenant-specific tokens
Tenant C (bearerToken injected by Integration Hub) ──┘
```

Each request carries its own authentication context via `bearerToken` which is:
1. Stored by Integration Hub after OAuth flow
2. Injected into tool arguments automatically at runtime
3. NOT defined in the tool's inputSchema (invisible to the LLM)
4. Used by the tool handler to make authenticated API calls

---

## File Structure

```
your-mcp-server/
├── package.json              # Dependencies (NO @modelcontextprotocol/sdk)
├── tsconfig.json             # TypeScript configuration
├── .env                      # Environment variables
├── assets/                   # Static brand assets
│   └── logos/
│       └── service-icon.svg  # Square icon for integration grid (32x32)
├── src/
│   ├── index.ts              # Main server with JSON-RPC 2.0 handler
│   ├── config/
│   │   └── envs.ts           # ALL environment variables centralized here
│   ├── routes/
│   │   └── auth.routes.ts    # Integration Hub compatibility (credentials, metadata, post-auth)
│   ├── middleware/
│   │   └── auth.middleware.ts # API key protection for auth endpoints
│   ├── tools/
│   │   ├── index.ts          # Tool registration and exports
│   │   └── [domain].tools.ts # Domain-specific tools (NO bearerToken in schemas)
│   ├── services/
│   │   └── api.service.ts    # HTTP API client (axios, no vendor SDK)
│   └── handlers/
│       └── post-auth.handler.ts  # Post-OAuth processing (if needed)
└── README.md
```

---

## Step-by-Step Implementation

### Step 1: Project Setup

```bash
# 1. Initialize project
npm init -y

# 2. Install dependencies (NO @modelcontextprotocol/sdk)
npm install express cors helmet dotenv axios

# 3. Install dev dependencies
npm install -D typescript @types/node @types/express @types/cors ts-node nodemon
```

**package.json:**

```json
{
  "name": "your-mcp-server",
  "version": "1.0.0",
  "description": "MCP Server - Direct JSON-RPC 2.0 Implementation",
  "main": "dist/index.js",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "nodemon --exec ts-node src/index.ts"
  },
  "dependencies": {
    "axios": "^1.6.0",
    "cors": "^2.8.5",
    "dotenv": "^16.4.5",
    "express": "^4.19.2",
    "helmet": "^7.1.0"
  },
  "devDependencies": {
    "@types/cors": "^2.8.17",
    "@types/express": "^4.17.21",
    "@types/node": "^20.12.7",
    "nodemon": "^3.1.0",
    "ts-node": "^10.9.2",
    "typescript": "^5.4.5"
  }
}
```

> **IMPORTANT**: Notice there is NO `@modelcontextprotocol/sdk` dependency. We handle JSON-RPC 2.0 directly.

---

### Step 2: Environment Configuration (envs.ts)

**CRITICAL**: ALL environment variables MUST be centralized in `src/config/envs.ts`. Never use `process.env` directly in other files.

```typescript
// src/config/envs.ts
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// ============================================================================
// SERVER CONFIGURATION
// ============================================================================

export const NODE_ENV = process.env['NODE_ENV'] || 'development';
export const HTTP_PORT = process.env['PORT'] || process.env['HTTP_PORT'] || 3000;

// Server metadata
export const YOURSERVICE_SERVER_NAME = process.env['YOURSERVICE_SERVER_NAME'] || 'YourService MCP Server';
export const YOURSERVICE_SERVER_VERSION = process.env['YOURSERVICE_SERVER_VERSION'] || '1.0.0';

// CORS configuration
export const CORS_ORIGIN = process.env['CORS_ORIGIN'] || '*';

// ============================================================================
// SERVICE-SPECIFIC CONFIGURATION (use SERVICE_* prefix consistently)
// ============================================================================

// OAuth Configuration
export const YOURSERVICE_CLIENT_ID = process.env['YOURSERVICE_CLIENT_ID'];
export const YOURSERVICE_CLIENT_SECRET = process.env['YOURSERVICE_CLIENT_SECRET'];
export const YOURSERVICE_AUTH_URL = process.env['YOURSERVICE_AUTH_URL'] || 'https://auth.yourservice.com/oauth/authorize';
export const YOURSERVICE_TOKEN_URL = process.env['YOURSERVICE_TOKEN_URL'] || 'https://auth.yourservice.com/oauth/token';
export const YOURSERVICE_REDIRECT_URI = process.env['YOURSERVICE_REDIRECT_URI'] || 'http://localhost:3000/auth/callback';
export const YOURSERVICE_SCOPES = process.env['YOURSERVICE_SCOPES'] || 'read,write';

// API Configuration
export const YOURSERVICE_API_BASE_URL = process.env['YOURSERVICE_API_BASE_URL'] || 'https://api.yourservice.com/v1';
export const YOURSERVICE_USER_AGENT = process.env['YOURSERVICE_USER_AGENT'] || 'Bixie-YourService-MCP-Server/1.0.0';

// ============================================================================
// SECURITY
// ============================================================================

export const INTERNAL_SERVICES_API_KEY = process.env['INTERNAL_SERVICES_API_KEY'];

// ============================================================================
// INTEGRATION HUB METADATA (all from env with sensible defaults)
// ============================================================================

export const YOURSERVICE_INTEGRATION_ID = process.env['YOURSERVICE_INTEGRATION_ID'] || 'yourservice';
export const YOURSERVICE_INTEGRATION_NAME = process.env['YOURSERVICE_INTEGRATION_NAME'] || 'Your Service';
export const YOURSERVICE_INTEGRATION_DESCRIPTION = process.env['YOURSERVICE_INTEGRATION_DESCRIPTION'] || 'Description of your service';
export const YOURSERVICE_INTEGRATION_CATEGORY = process.env['YOURSERVICE_INTEGRATION_CATEGORY'] || 'Business';
export const YOURSERVICE_INTEGRATION_RATING = parseFloat(process.env['YOURSERVICE_INTEGRATION_RATING'] || '4.8');
export const YOURSERVICE_INTEGRATION_INSTALLS = process.env['YOURSERVICE_INTEGRATION_INSTALLS'] || '10K+';
export const YOURSERVICE_INTEGRATION_FEATURES = process.env['YOURSERVICE_INTEGRATION_FEATURES']?.split(',') || [
  'Feature 1',
  'Feature 2',
  'Feature 3'
];
export const YOURSERVICE_INTEGRATION_CAPABILITIES = {
  webhooks: process.env['YOURSERVICE_INTEGRATION_WEBHOOKS'] === 'true' || false,
  realTimeSync: process.env['YOURSERVICE_INTEGRATION_REALTIME_SYNC'] === 'true' || false,
  batchOperations: process.env['YOURSERVICE_INTEGRATION_BATCH_OPERATIONS'] === 'true' || true
};
export const YOURSERVICE_INTEGRATION_ICON = process.env['YOURSERVICE_INTEGRATION_ICON'] || '/assets/logos/yourservice-icon.svg';
export const YOURSERVICE_INTEGRATION_COLOR = process.env['YOURSERVICE_INTEGRATION_COLOR'] || '#000000';
export const YOURSERVICE_INTEGRATION_BACKGROUND_COLOR = process.env['YOURSERVICE_INTEGRATION_BACKGROUND_COLOR'] || '#FFFFFF';

// ============================================================================
// LOGGING & RATE LIMITING
// ============================================================================

export const LOG_LEVEL = process.env['LOG_LEVEL'] || 'info';
export const ENABLE_DEBUG_LOGGING = process.env['ENABLE_DEBUG_LOGGING'] === 'true';
export const YOURSERVICE_RATE_LIMIT_REQUESTS_PER_MINUTE = parseInt(process.env['YOURSERVICE_RATE_LIMIT_REQUESTS_PER_MINUTE'] || '200', 10);
export const YOURSERVICE_RATE_LIMIT_BURST_SIZE = parseInt(process.env['YOURSERVICE_RATE_LIMIT_BURST_SIZE'] || '50', 10);

// ============================================================================
// VALIDATION
// ============================================================================

export function validateRequiredConfig(): void {
  const required = [
    { key: 'YOURSERVICE_CLIENT_ID', value: YOURSERVICE_CLIENT_ID },
    { key: 'YOURSERVICE_CLIENT_SECRET', value: YOURSERVICE_CLIENT_SECRET },
    { key: 'INTERNAL_SERVICES_API_KEY', value: INTERNAL_SERVICES_API_KEY },
  ];

  const missing = required.filter(({ value }) => !value);
  
  if (missing.length > 0) {
    const missingKeys = missing.map(({ key }) => key).join(', ');
    console.warn(`Warning: Missing environment variables: ${missingKeys}`);
    console.warn('OAuth functionality will be limited without proper configuration');
  }
}

// ============================================================================
// CONFIG EXPORT (single object for convenience)
// ============================================================================

export const CONFIG = {
  NODE_ENV,
  HTTP_PORT,
  YOURSERVICE_SERVER_NAME,
  YOURSERVICE_SERVER_VERSION,
  CORS_ORIGIN,
  YOURSERVICE_CLIENT_ID,
  YOURSERVICE_CLIENT_SECRET,
  YOURSERVICE_AUTH_URL,
  YOURSERVICE_TOKEN_URL,
  YOURSERVICE_REDIRECT_URI,
  YOURSERVICE_SCOPES,
  YOURSERVICE_API_BASE_URL,
  YOURSERVICE_USER_AGENT,
  INTERNAL_SERVICES_API_KEY,
  YOURSERVICE_INTEGRATION_ID,
  YOURSERVICE_INTEGRATION_NAME,
  YOURSERVICE_INTEGRATION_DESCRIPTION,
  YOURSERVICE_INTEGRATION_CATEGORY,
  YOURSERVICE_INTEGRATION_RATING,
  YOURSERVICE_INTEGRATION_INSTALLS,
  YOURSERVICE_INTEGRATION_FEATURES,
  YOURSERVICE_INTEGRATION_CAPABILITIES,
  YOURSERVICE_INTEGRATION_ICON,
  YOURSERVICE_INTEGRATION_COLOR,
  YOURSERVICE_INTEGRATION_BACKGROUND_COLOR,
  LOG_LEVEL,
  ENABLE_DEBUG_LOGGING,
  YOURSERVICE_RATE_LIMIT_REQUESTS_PER_MINUTE,
  YOURSERVICE_RATE_LIMIT_BURST_SIZE,
} as const;

export type AppConfig = typeof CONFIG;
```

**Environment Variable Naming Convention:**

| Service | Prefix | Examples |
|---------|--------|---------|
| Gmail | `GMAIL_*` | `GMAIL_CLIENT_ID`, `GMAIL_AUTH_URL`, `GMAIL_API_BASE_URL` |
| Slack | `SLACK_*` | `SLACK_CLIENT_ID`, `SLACK_SIGNING_SECRET`, `SLACK_SCOPES` |
| Apollo | `APOLLO_*` | `APOLLO_CLIENT_ID`, `APOLLO_AUTH_URL`, `APOLLO_API_BASE_URL` |
| QuickBooks | `QUICKBOOKS_*` | `QUICKBOOKS_CLIENT_ID`, `QUICKBOOKS_ENVIRONMENT` |
| DocuSign | `DOCUSIGN_*` | `DOCUSIGN_CLIENT_ID`, `DOCUSIGN_AUTH_URL` |

---

### Step 3: Main Server (index.ts)

This is the core pattern used by all our production servers (Gmail, Apollo, Slack). No MCP SDK required.

```typescript
// src/index.ts
#!/usr/bin/env node

import 'dotenv/config';
import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { randomUUID } from 'node:crypto';

// Import routes and tools
import authRoutes from './routes/auth.routes.js';
import { yourServiceTools, initializeTools } from './tools/index.js';
import { 
  HTTP_PORT, 
  CORS_ORIGIN, 
  YOURSERVICE_SERVER_NAME, 
  YOURSERVICE_SERVER_VERSION,
  validateRequiredConfig 
} from './config/envs.js';

// Helper function to mask sensitive data in logs
const maskSensitiveData = (obj: any): any => {
  if (!obj || typeof obj !== 'object') return obj;
  
  const masked = { ...obj };
  const sensitiveKeys = ['bearerToken', 'authToken', 'token', 'password', 'secret', 'key', 'authorization'];
  
  for (const key in masked) {
    if (sensitiveKeys.some(sensitiveKey => key.toLowerCase().includes(sensitiveKey.toLowerCase()))) {
      if (typeof masked[key] === 'string' && masked[key].length > 8) {
        masked[key] = masked[key].substring(0, 8) + '...';
      }
    } else if (typeof masked[key] === 'object' && masked[key] !== null) {
      masked[key] = maskSensitiveData(masked[key]);
    }
  }
  
  return masked;
};

// Helper function to get tool by name
const getToolByName = (name: string) => {
  return yourServiceTools.find(({ tool }) => tool.name === name);
};

// Helper function to get tool stats
const getToolStats = () => {
  return {
    totalTools: yourServiceTools.length,
    tools: yourServiceTools.map(t => t.tool.name)
  };
};

const app: Express = express();

// Security middleware
app.use(helmet());

// CORS middleware
app.use(cors({
  origin: CORS_ORIGIN,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true
}));

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Request logging middleware
app.use((req: Request, res: Response, next: NextFunction) => {
  if (req.path === '/mcp' || req.path.startsWith('/api/v1/tools')) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] ${req.method} ${req.path} - ${req.ip}`);
  }
  next();
});

// Serve static brand assets
app.use('/assets', express.static('assets'));

// Health check endpoint
app.get('/health', (req: Request, res: Response) => {
  const stats = getToolStats();
  res.json({
    status: 'UP',
    timestamp: new Date().toISOString(),
    server: YOURSERVICE_SERVER_NAME,
    version: YOURSERVICE_SERVER_VERSION,
    environment: process.env.NODE_ENV || 'development',
    tools: {
      total: stats.totalTools
    }
  });
});

// Integration Hub compatibility routes
app.use('/auth', authRoutes);

// Error handling middleware
app.use((err: any, req: Request, res: Response, next: NextFunction) => {
  console.error('[ERROR] Server error:', err.message || err);
  res.status(err.status || 500).json({
    success: false,
    error: err.message || 'Internal server error',
    timestamp: new Date().toISOString()
  });
});

// =============================================================================
// JSON-RPC 2.0 MCP ENDPOINT (NO MCP SDK REQUIRED)
// =============================================================================

app.post('/mcp', async (req: Request, res: Response) => {
  try {
    const { method, params, id } = req.body;
    
    console.log(`[MCP] Received request: ${method}`);
    
    switch (method) {
      case 'initialize':
        res.json({
          jsonrpc: '2.0',
          id,
          result: {
            protocolVersion: '2024-11-05',
            capabilities: {
              tools: {},
              logging: {}
            },
            serverInfo: {
              name: 'yourservice-mcp-server',
              version: YOURSERVICE_SERVER_VERSION
            }
          }
        });
        break;
        
      case 'tools/list':
        const tools = yourServiceTools.map(({ tool }) => ({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
          ...(tool.outputSchema && { outputSchema: tool.outputSchema })
        }));
        
        console.log(`[MCP] Returning ${tools.length} tools with output schemas`);
        res.json({
          jsonrpc: '2.0',
          id,
          result: { tools }
        });
        break;
        
      case 'tools/call':
        const { name, arguments: args } = params;
        const toolArgs = args || {};
        
        console.log(`[MCP] Executing tool: ${name}`);
        console.log(`[MCP] Tool args:`, JSON.stringify(maskSensitiveData(toolArgs), null, 2));
        
        // Validate authentication is present
        // bearerToken is injected by Integration Hub - NOT defined in tool schemas
        if (!toolArgs.bearerToken && !toolArgs.accessToken && !toolArgs.apiKey) {
          console.log(`[MCP] Authentication missing for ${name}`);
          res.json({
            jsonrpc: '2.0',
            id,
            error: {
              code: -32602,
              message: `Authentication required: bearerToken, accessToken, or apiKey missing for ${name}`
            }
          });
          return;
        }
        
        const toolRegistration = getToolByName(name);
        if (!toolRegistration) {
          console.log(`[MCP] Tool not found: ${name}`);
          res.json({
            jsonrpc: '2.0',
            id,
            error: {
              code: -32601,
              message: `Tool '${name}' not found`
            }
          });
          return;
        }
        
        try {
          const result = await toolRegistration.handler(toolArgs);
          
          console.log(`[MCP] Tool ${name} executed successfully`);
          res.json({
            jsonrpc: '2.0',
            id,
            result
          });
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Tool execution failed';
          console.error(`[MCP] Tool ${name} failed:`, errorMessage);
          
          res.json({
            jsonrpc: '2.0',
            id,
            error: {
              code: -32603,
              message: `Tool execution failed: ${errorMessage}`
            }
          });
        }
        break;
        
      case 'notifications/initialized':
        res.json({ jsonrpc: '2.0', id });
        break;
        
      default:
        console.log(`[MCP] Unknown method: ${method}`);
        res.json({
          jsonrpc: '2.0',
          id,
          error: {
            code: -32601,
            message: `Method '${method}' not found`
          }
        });
        break;
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Internal error';
    console.error('[MCP] Error processing request:', errorMessage);
    
    res.json({
      jsonrpc: '2.0',
      id: req.body?.id || null,
      error: {
        code: -32603,
        message: errorMessage
      }
    });
  }
});

// Catch-all route
app.use('*', (req: Request, res: Response) => {
  res.status(404).json({
    success: false,
    error: 'Route not found',
    path: req.originalUrl,
    timestamp: new Date().toISOString()
  });
});

// Start the server
app.listen(HTTP_PORT, async () => {
  console.log(`\n${YOURSERVICE_SERVER_NAME} running on port ${HTTP_PORT}`);
  
  // Validate required configuration
  try {
    validateRequiredConfig();
  } catch (error) {
    console.error('Configuration validation failed:', error);
    process.exit(1);
  }
  
  // Initialize tools
  await initializeTools();
  
  const stats = getToolStats();
  console.log(`Base URL: http://localhost:${HTTP_PORT}`);
  console.log(`Health check: http://localhost:${HTTP_PORT}/health`);
  console.log(`MCP Endpoint: http://localhost:${HTTP_PORT}/mcp`);
  console.log(`Total tools: ${stats.totalTools}`);
  console.log(`Authentication: Bearer token (injected by Integration Hub)`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`\nReady to serve API tools!`);
});
```

---

### Step 4: Auth Routes (auth.routes.ts)

The auth routes provide Integration Hub compatibility with endpoints for OAuth credentials, integration metadata, post-OAuth processing, and pre-OAuth variable collection.

```typescript
// src/routes/auth.routes.ts
import { Router, Request, Response } from 'express';
import { verifyInternalService } from '../middleware/auth.middleware.js';
import {
  YOURSERVICE_CLIENT_ID,
  YOURSERVICE_CLIENT_SECRET,
  YOURSERVICE_AUTH_URL,
  YOURSERVICE_TOKEN_URL,
  YOURSERVICE_REDIRECT_URI,
  YOURSERVICE_SCOPES,
  YOURSERVICE_INTEGRATION_ID,
  YOURSERVICE_INTEGRATION_NAME,
  YOURSERVICE_INTEGRATION_DESCRIPTION,
  YOURSERVICE_INTEGRATION_CATEGORY,
  YOURSERVICE_INTEGRATION_RATING,
  YOURSERVICE_INTEGRATION_INSTALLS,
  YOURSERVICE_INTEGRATION_FEATURES,
  YOURSERVICE_INTEGRATION_CAPABILITIES,
  YOURSERVICE_INTEGRATION_ICON,
  YOURSERVICE_INTEGRATION_COLOR,
  YOURSERVICE_INTEGRATION_BACKGROUND_COLOR,
  YOURSERVICE_SERVER_VERSION
} from '../config/envs.js';

const router = Router();

// ============================================================================
// GET /auth/credentials/:integrationId
// Returns OAuth credentials for Integration Hub
// ============================================================================

router.get('/credentials/:integrationId', verifyInternalService, (req: Request, res: Response) => {
  const { integrationId } = req.params;

  if (!integrationId || integrationId.toLowerCase() !== YOURSERVICE_INTEGRATION_ID) {
    return res.status(404).json({
      success: false,
      error: `Integration '${integrationId}' not supported`
    });
  }

  const credentials = {
    clientId: YOURSERVICE_CLIENT_ID,
    clientSecret: YOURSERVICE_CLIENT_SECRET,
    authUrl: YOURSERVICE_AUTH_URL,
    tokenUrl: YOURSERVICE_TOKEN_URL,
    redirectUri: YOURSERVICE_REDIRECT_URI,
    scopes: YOURSERVICE_SCOPES?.split(',') || [],
    integrationId: YOURSERVICE_INTEGRATION_ID,
    responseType: 'code'
  };

  console.log('[AUTH] Returning OAuth credentials');
  res.json(credentials);
});

// ============================================================================
// GET /auth/metadata/:integrationId
// Returns integration metadata for Integration Hub display
// ============================================================================

router.get('/metadata/:integrationId', verifyInternalService, (req: Request, res: Response) => {
  const { integrationId } = req.params;

  if (!integrationId || integrationId.toLowerCase() !== YOURSERVICE_INTEGRATION_ID) {
    return res.status(404).json({
      success: false,
      error: `Integration '${integrationId}' not supported`
    });
  }

  const metadata = {
    id: YOURSERVICE_INTEGRATION_ID,
    name: YOURSERVICE_INTEGRATION_NAME,
    description: YOURSERVICE_INTEGRATION_DESCRIPTION,
    category: YOURSERVICE_INTEGRATION_CATEGORY,
    type: 'oauth' as const,
    rating: YOURSERVICE_INTEGRATION_RATING,
    installs: YOURSERVICE_INTEGRATION_INSTALLS,
    features: YOURSERVICE_INTEGRATION_FEATURES,
    capabilities: YOURSERVICE_INTEGRATION_CAPABILITIES,

    // Enable post-auth callback (Integration Hub will call /auth/post-auth)
    // Set to true if you need to extract data after OAuth token exchange
    postOAuthActions: true,

    // Pre-OAuth variables (optional - only if you need user input before OAuth)
    // See "Pre-OAuth Actions" section for details
    // preOAuthActions: true,
    // preOAuthActionVariables: [ ... ],

    // Brand assets
    icon: YOURSERVICE_INTEGRATION_ICON,
    color: YOURSERVICE_INTEGRATION_COLOR,
    brandAssets: {
      squareIcon: YOURSERVICE_INTEGRATION_ICON,
      primaryColor: YOURSERVICE_INTEGRATION_COLOR,
      backgroundColor: YOURSERVICE_INTEGRATION_BACKGROUND_COLOR
    }
  };

  console.log('[AUTH] Returning integration metadata');
  res.json(metadata);
});

// ============================================================================
// POST /auth/post-auth
// Called by Integration Hub after OAuth token exchange
// Returns contextData (merged with preOAuth data, passed to all tool calls)
// and other metadata (saved to DB but NOT passed to tool calls)
// ============================================================================

router.post('/post-auth', verifyInternalService, async (req: Request, res: Response) => {
  const { accessToken, tokenResponse, callbackQueryData } = req.body;

  console.log('[AUTH] Processing post-auth');

  try {
    // Extract data from token response or callback query data
    // What you extract depends on the service (see examples below)

    // Build contextData - these items will be:
    //   1. Merged with any pre-OAuth contextData already saved
    //   2. Saved to DB
    //   3. Passed to ALL tool executions internally (alongside bearerToken)
    const contextData: Record<string, any> = {
      // Add service-specific identifiers needed for every API call
      // Examples:
      //   QuickBooks: { realmId: '123456' }
      //   DocuSign:   { accountId: 'abc', baseUrl: 'https://...', accountName: 'My Account' }
      //   Xero:       { tenantId: 'xyz', tenantName: 'My Org' }
      //   Slack:      (workspace info extracted from tokenResponse)
    };

    // Build additional metadata - these will be:
    //   1. Saved directly to DB for future reference
    //   2. NOT sent with each tool call internally
    const additionalMetadata: Record<string, any> = {
      // Add supplementary information for auditing/display
      // Examples:
      //   userId, userEmail, userName
      //   organizationId, organizationName
      //   isDefault, authEventId
    };

    console.log('[AUTH] Post-auth data extracted successfully');

    // Return in the format expected by Integration Hub
    res.json({
      success: true,
      data: {
        contextData,
        // Additional keys saved to DB but NOT passed to tool calls
        // Name this whatever makes sense: accountMetadata, tenantMetadata, integrationDetails, etc.
        accountMetadata: additionalMetadata
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('[AUTH] Error processing post-auth:', error);
    
    // Return success with empty data to not block OAuth completion
    res.json({
      success: true,
      data: {},
      timestamp: new Date().toISOString(),
      error: `Failed to process post-auth: ${error instanceof Error ? error.message : 'Unknown error'}`
    });
  }
});

// ============================================================================
// GET /auth/status
// Health check for authentication configuration
// ============================================================================

router.get('/status', verifyInternalService, (_req: Request, res: Response) => {
  const status = {
    success: true,
    status: 'healthy',
    timestamp: new Date().toISOString(),
    integration: {
      id: YOURSERVICE_INTEGRATION_ID,
      name: YOURSERVICE_INTEGRATION_NAME,
      version: YOURSERVICE_SERVER_VERSION,
      oauth: {
        configured: !!(YOURSERVICE_CLIENT_ID && YOURSERVICE_CLIENT_SECRET),
        scopes: YOURSERVICE_SCOPES?.split(',') || []
      }
    }
  };

  console.log('[AUTH] Returning auth status');
  res.json(status);
});

export default router;
```

---

### Step 5: Security Middleware

```typescript
// src/middleware/auth.middleware.ts
import { Request, Response, NextFunction } from 'express';

export const verifyInternalService = (req: Request, res: Response, next: NextFunction): void => {
  const internalApiKey = process.env['INTERNAL_SERVICES_API_KEY'];

  if (!internalApiKey) {
    res.status(500).json({ 
      success: false, 
      error: 'Internal service authentication not configured' 
    });
    return;
  }

  // Accept API key from multiple header formats
  const providedKey = req.headers['x-service-secret'] || 
                     req.headers['x-internal-api-key'] || 
                     req.headers['authorization']?.replace('Bearer ', '');

  if (!providedKey) {
    res.status(401).json({ 
      success: false, 
      error: 'Internal API key required' 
    });
    return;
  }

  if (providedKey !== internalApiKey) {
    res.status(403).json({ 
      success: false, 
      error: 'Invalid internal API key' 
    });
    return;
  }

  next();
};
```

---

### Step 6: Tool Definitions

**CRITICAL: Do NOT include `bearerToken` in tool inputSchema.** The Integration Hub injects `bearerToken` (and `contextData` fields) into tool arguments automatically at runtime. The LLM should not know about authentication.

```typescript
// src/tools/yourservice.tools.ts

import { makeApiCall } from '../services/api.service.js';

// Helper function for MCP responses
export const createMcpResponse = (data: any, message?: string) => {
  return {
    content: [{
      type: "text" as const,
      text: JSON.stringify({
        success: data.success !== false,
        data: data.data || data,
        ...(data.timestamp && { timestamp: data.timestamp }),
        ...(message && { message }),
        ...(data.error && { error: data.error })
      }, null, 2)
    }]
  };
};

// =============================================================================
// INPUT SCHEMAS - NO bearerToken! It is injected by Integration Hub internally
// =============================================================================

const listItemsSchema = {
  type: 'object',
  properties: {
    // Only business-relevant parameters go here
    query: {
      type: 'string',
      description: 'Search query to filter items'
    },
    maxResults: {
      type: 'number',
      minimum: 1,
      maximum: 100,
      default: 20,
      description: 'Maximum number of items to return (1-100, default 20)'
    },
    pageToken: {
      type: 'string',
      description: 'Page token for pagination'
    },
    status: {
      type: 'string',
      enum: ['active', 'inactive', 'archived'],
      description: 'Filter by item status'
    }
  }
  // Note: NO required array with bearerToken - it's handled internally
};

const getItemSchema = {
  type: 'object',
  properties: {
    id: {
      type: 'string',
      description: 'Unique item identifier'
    }
  },
  required: ['id']
};

const createItemSchema = {
  type: 'object',
  properties: {
    name: {
      type: 'string',
      description: 'Item name',
      minLength: 1,
      maxLength: 255
    },
    description: {
      type: 'string',
      description: 'Item description'
    },
    category: {
      type: 'string',
      description: 'Item category'
    }
  },
  required: ['name']
};

// =============================================================================
// OUTPUT SCHEMAS (for LLM understanding of response structure)
// =============================================================================

const listItemsOutputSchema = {
  type: 'object',
  properties: {
    success: { type: 'boolean', description: 'Whether the operation succeeded' },
    data: {
      type: 'object',
      properties: {
        items: {
          type: 'array',
          description: 'Array of items',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string', description: 'Item ID' },
              name: { type: 'string', description: 'Item name' },
              status: { type: 'string', description: 'Item status' }
            }
          }
        },
        nextPageToken: { type: 'string', description: 'Token for next page' }
      }
    },
    timestamp: { type: 'string', description: 'Response timestamp' }
  },
  required: ['success', 'data']
};

// =============================================================================
// TOOL HANDLERS
// bearerToken arrives in args (injected by Integration Hub), but NOT in schema
// contextData fields also arrive in args (merged from pre-oauth + post-auth)
// =============================================================================

export const listItemsHandler = async (args: any) => {
  try {
    // bearerToken is available in args (injected by Integration Hub)
    const { bearerToken, ...params } = args;
    
    const response = await makeApiCall('/items', bearerToken, 'GET', undefined, params);
    return createMcpResponse(response, 'Items retrieved successfully');
  } catch (error) {
    return createMcpResponse({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
};

export const getItemHandler = async (args: any) => {
  try {
    const { bearerToken, id } = args;
    
    const response = await makeApiCall(`/items/${id}`, bearerToken, 'GET');
    return createMcpResponse(response, 'Item retrieved successfully');
  } catch (error) {
    return createMcpResponse({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
};

export const createItemHandler = async (args: any) => {
  try {
    const { bearerToken, ...params } = args;
    
    const response = await makeApiCall('/items', bearerToken, 'POST', params);
    return createMcpResponse(response, 'Item created successfully');
  } catch (error) {
    return createMcpResponse({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
};

// =============================================================================
// TOOL EXPORTS
// =============================================================================

export const yourServiceTools = [
  {
    tool: {
      name: 'yourservice.list_items',
      description: 'List items from YourService with optional filtering and pagination',
      inputSchema: listItemsSchema,
      outputSchema: listItemsOutputSchema
    },
    handler: listItemsHandler
  },
  {
    tool: {
      name: 'yourservice.get_item',
      description: 'Get a single item by ID',
      inputSchema: getItemSchema
    },
    handler: getItemHandler
  },
  {
    tool: {
      name: 'yourservice.create_item',
      description: 'Create a new item in YourService',
      inputSchema: createItemSchema
    },
    handler: createItemHandler
  }
];
```

**Tool index file:**

```typescript
// src/tools/index.ts
import { yourServiceTools as tools } from './yourservice.tools.js';

// Export tools as static array
export const yourServiceTools = tools;

// Initialize tools function
export async function initializeTools() {
  console.log(`Loaded ${yourServiceTools.length} tools`);
  return yourServiceTools;
}
```

---

### Step 7: API Service Layer

```typescript
// src/services/api.service.ts
import axios from 'axios';
import { YOURSERVICE_API_BASE_URL, YOURSERVICE_USER_AGENT } from '../config/envs.js';

export const makeApiCall = async (
  endpoint: string,
  bearerToken: string,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
  data?: any,
  params?: any
) => {
  const fullUrl = `${YOURSERVICE_API_BASE_URL}${endpoint}`;
  
  console.log(`[API] ${method} ${fullUrl}`);

  try {
    const response = await axios({
      method,
      url: fullUrl,
      headers: {
        'Authorization': `Bearer ${bearerToken}`,
        'Content-Type': 'application/json',
        'User-Agent': YOURSERVICE_USER_AGENT
      },
      ...(data && { data }),
      ...(params && { params }),
      timeout: 30000
    });

    return {
      success: true,
      data: response.data,
      timestamp: new Date().toISOString()
    };
  } catch (error: any) {
    console.error(`[API] Error:`, {
      status: error.response?.status,
      message: error.response?.data?.message || error.message
    });
    
    return {
      success: false,
      error: error.response?.data?.message || error.message || 'API call failed',
      statusCode: error.response?.status,
      timestamp: new Date().toISOString()
    };
  }
};
```

---

## Authentication & Bearer Token Handling

### How Authentication Works

The Integration Hub manages the entire OAuth flow and token lifecycle. MCP servers do NOT need to handle tokens in their tool schemas.

```
1. User connects via Integration Hub
2. Integration Hub performs OAuth flow using credentials from /auth/credentials
3. Integration Hub stores access_token (and refresh_token)
4. When a tool is called:
   a. Integration Hub injects bearerToken into tool arguments
   b. Integration Hub also injects contextData fields into tool arguments
   c. MCP server receives args with bearerToken already present
   d. Tool handler extracts bearerToken and uses it for API calls
```

### What This Means for Tool Schemas

```typescript
// WRONG - Do NOT include bearerToken in inputSchema
const myToolSchema = {
  type: 'object',
  properties: {
    bearerToken: { type: 'string', description: 'OAuth bearer token' },  // NO!
    query: { type: 'string', description: 'Search query' }
  },
  required: ['bearerToken', 'query']  // NO!
};

// CORRECT - Only business parameters in inputSchema
const myToolSchema = {
  type: 'object',
  properties: {
    query: { type: 'string', description: 'Search query' }
  },
  required: ['query']
};

// The handler still receives bearerToken (injected by Integration Hub)
const myToolHandler = async (args: any) => {
  const { bearerToken, query } = args;  // bearerToken is here at runtime
  // Use bearerToken for API calls...
};
```

### Bearer Token Validation in /mcp Endpoint

Even though bearerToken is not in the schema, the `/mcp` endpoint should validate it is present at runtime:

```typescript
case 'tools/call':
  const toolArgs = args || {};
  
  // Validate authentication is present (injected by Integration Hub)
  if (!toolArgs.bearerToken && !toolArgs.accessToken && !toolArgs.apiKey) {
    res.json({
      jsonrpc: '2.0',
      id,
      error: {
        code: -32602,
        message: `Authentication required for ${name}`
      }
    });
    return;
  }
```

---

## Pre-OAuth Actions

Pre-OAuth actions allow you to collect information from the user BEFORE the OAuth flow begins. This is useful when:
- The service requires a specific region/data center selection
- OAuth URLs are dynamic (based on user's instance URL)
- Additional identifiers are needed (company domain, shop name, etc.)

### How Pre-OAuth Works

```
1. Integration Hub calls GET /auth/metadata/:integrationId
2. Metadata includes preOAuthActions: true and preOAuthActionVariables array
3. Integration Hub displays a form to collect these variables from the user
4. User fills in the variables (e.g., selects region)
5. Variables are saved as contextData in the DB
6. Integration Hub proceeds with OAuth flow
7. If post-auth also returns contextData, it is MERGED with pre-OAuth contextData
8. Final merged contextData is passed to ALL tool executions
```

### Metadata Configuration

Add these fields to the metadata response in `auth.routes.ts`:

```typescript
const metadata = {
  // ... other metadata fields ...

  // Enable pre-OAuth variable collection
  preOAuthActions: true,
  preOAuthActionVariables: [
    {
      key: 'region',                              // Variable key (saved in contextData)
      label: 'Data Center Region',                // Display label for user
      type: 'select',                             // Input type: 'select', 'text', 'password'
      required: true,                             // Is this required?
      options: [                                  // Options for 'select' type
        { value: 'com', label: 'United States (.com)' },
        { value: 'eu', label: 'Europe (.eu)' },
        { value: 'in', label: 'India (.in)' },
        { value: 'com.au', label: 'Australia (.com.au)' }
      ],
      default: 'com',                            // Default value
      description: 'Select your data center region'
    }
  ]
};
```

### Real-World Examples

**Zoho Services (region-based OAuth URLs):**

```typescript
preOAuthActions: true,
preOAuthActionVariables: [
  {
    key: 'region',
    label: 'Zoho Data Center',
    type: 'select',
    required: true,
    options: [
      { value: 'com', label: 'United States (.com)' },
      { value: 'eu', label: 'Europe (.eu)' },
      { value: 'in', label: 'India (.in)' },
      { value: 'com.au', label: 'Australia (.com.au)' },
      { value: 'uk', label: 'United Kingdom (.uk)' },
      { value: 'com.cn', label: 'China (.com.cn)' }
    ],
    default: 'com',
    description: 'Select your Zoho data center region'
  }
]
```

**Salesforce (custom instance URL):**

```typescript
preOAuthActions: true,
preOAuthActionVariables: [
  {
    key: 'instanceUrl',
    label: 'Salesforce Instance URL',
    type: 'text',
    required: true,
    default: 'https://login.salesforce.com',
    description: 'Your Salesforce login URL (e.g., https://login.salesforce.com or https://mycompany.my.salesforce.com)'
  }
]
```

**Shopify (shop domain):**

```typescript
preOAuthActions: true,
preOAuthActionVariables: [
  {
    key: 'shopDomain',
    label: 'Shop Name',
    type: 'text',
    required: true,
    description: 'Your Shopify shop name (e.g., "mystore" from mystore.myshopify.com)'
  }
]
```

**BambooHR (company subdomain):**

```typescript
preOAuthActions: true,
preOAuthActionVariables: [
  {
    key: 'companyDomain',
    label: 'BambooHR Subdomain',
    type: 'text',
    required: true,
    description: 'Your BambooHR subdomain (e.g., "mycompany" from mycompany.bamboohr.com)'
  }
]
```

---

## Post-OAuth Actions & contextData

Post-OAuth actions allow the MCP server to extract additional information after the OAuth token exchange is complete. This is critical for services that require additional identifiers for API calls.

### How Post-OAuth Works

```
1. User completes OAuth flow
2. Integration Hub exchanges authorization code for tokens
3. Integration Hub calls POST /auth/post-auth with:
   - accessToken: The newly obtained access token
   - tokenResponse: Full token response from the OAuth provider
   - callbackQueryData: Query parameters from the OAuth callback URL
4. MCP server extracts required data (makes API calls if needed)
5. MCP server returns response with contextData and additional metadata
6. Integration Hub saves everything to DB
```

### Response Format

The post-auth response has a specific format where **contextData** and **other keys** behave differently:

```typescript
res.json({
  success: true,
  data: {
    // contextData: MERGED with pre-OAuth contextData, PASSED to ALL tool calls internally
    contextData: {
      realmId: '123456789',       // QuickBooks company ID
      accountId: 'abc-def-123',   // DocuSign account ID
      baseUrl: 'https://...',     // Service-specific base URL
      tenantId: 'xyz-789',        // Xero tenant ID
      tenantName: 'My Company'    // Xero tenant name
    },
    
    // Other keys: SAVED to DB for reference, but NOT passed to tool calls
    accountMetadata: {
      userId: 'user-123',
      userEmail: 'user@example.com',
      userName: 'John Doe',
      organizationId: 'org-456',
      organizationName: 'Acme Corp',
      isDefault: true,
      authEventId: 'event-789'
    }
  },
  timestamp: new Date().toISOString()
});
```

### contextData Behavior Summary

| Field | Stored in DB | Merged with Pre-OAuth | Passed to Tool Calls |
|-------|-------------|----------------------|---------------------|
| `contextData.*` | Yes | Yes (merged) | Yes (injected into every tool call) |
| `accountMetadata.*` | Yes | No | No |
| `tenantMetadata.*` | Yes | No | No |
| `integrationDetails.*` | Yes | No | No |

### Real-World Examples

**QuickBooks** (extract realmId from callback query data):

```typescript
router.post('/post-auth', verifyInternalService, async (req, res) => {
  const { callbackQueryData, tokenResponse } = req.body;

  let realmId: string | undefined;

  // Extract realmId from callback query parameters
  if (callbackQueryData) {
    if (typeof callbackQueryData === 'object') {
      realmId = callbackQueryData.realmId || callbackQueryData.realm_id;
    } else if (typeof callbackQueryData === 'string') {
      const params = new URLSearchParams(callbackQueryData);
      realmId = params.get('realmId') || undefined;
    }
  }

  res.json({
    success: true,
    data: {
      contextData: {
        realmId: realmId  // Passed to ALL tool calls
      }
    },
    timestamp: new Date().toISOString()
  });
});
```

**DocuSign** (make API call to get account info):

```typescript
router.post('/post-auth', verifyInternalService, async (req, res) => {
  const { accessToken, tokenResponse } = req.body;

  // Make API call to get user info
  const userInfo = await docusignApiService.getUserInfo(accessToken);
  const defaultAccount = userInfo.accounts.find(a => a.is_default) || userInfo.accounts[0];

  res.json({
    success: true,
    data: {
      // contextData: passed to ALL tool calls
      contextData: {
        accountId: defaultAccount.account_id,
        baseUrl: defaultAccount.base_uri,
        accountName: defaultAccount.account_name
      },
      // accountMetadata: saved to DB only, NOT passed to tool calls
      accountMetadata: {
        userId: userInfo.sub,
        userEmail: userInfo.email,
        userName: userInfo.name,
        organizationId: defaultAccount.organization_id
      }
    },
    timestamp: new Date().toISOString()
  });
});
```

**Slack** (extract workspace info from token response):

```typescript
router.post('/post-auth', verifyInternalService, (req, res) => {
  const { tokenResponse } = req.body;

  let integrationDetails: Record<string, any> = {};

  if (tokenResponse) {
    if (tokenResponse.team) {
      integrationDetails.workspace = {
        id: tokenResponse.team.id,
        name: tokenResponse.team.name
      };
    }
    if (tokenResponse.authed_user) {
      integrationDetails.authedUser = {
        id: tokenResponse.authed_user.id
      };
    }
    if (tokenResponse.app_id) {
      integrationDetails.appId = tokenResponse.app_id;
    }
  }

  res.json({
    success: true,
    data: {
      integrationDetails  // Saved to DB, not passed to tool calls
    },
    timestamp: new Date().toISOString()
  });
});
```

### Using contextData in Tool Handlers

When a tool is called, the Integration Hub injects both `bearerToken` and all `contextData` fields into the tool arguments:

```typescript
// What the tool handler receives at runtime:
const handler = async (args: any) => {
  // args contains:
  // - bearerToken: 'ya29.abc...'          (from stored OAuth token)
  // - realmId: '123456789'                (from contextData - QuickBooks)
  // - accountId: 'abc-def-123'            (from contextData - DocuSign)
  // - baseUrl: 'https://...'              (from contextData - DocuSign)
  // - region: 'com'                       (from pre-OAuth contextData - Zoho)
  // - ...plus any business parameters the LLM provided

  const { bearerToken, realmId, ...params } = args;
  
  // Use contextData fields for API calls
  const url = `https://api.quickbooks.com/v3/company/${realmId}/items`;
  const response = await axios.get(url, {
    headers: { 'Authorization': `Bearer ${bearerToken}` }
  });
};
```

---

## Integration Hub Compatibility

### Required Endpoints

| Endpoint | Method | Purpose | Protection |
|----------|--------|---------|------------|
| `/auth/credentials/:id` | GET | OAuth credentials | API Key |
| `/auth/metadata/:id` | GET | Integration metadata | API Key |
| `/auth/post-auth` | POST | Post-OAuth data extraction | API Key |
| `/auth/status` | GET | Configuration health | API Key |
| `/health` | GET | Server health | Open |
| `/mcp` | POST | MCP tool calls | Open (bearerToken in args) |

### Metadata Flags Summary

| Flag | Purpose | When to Use |
|------|---------|-------------|
| `postOAuthActions: true` | Enable POST /auth/post-auth callback | When you need to extract data after OAuth (realmId, accountId, etc.) |
| `preOAuthActions: true` | Enable pre-OAuth variable collection | When you need user input before OAuth (region, instance URL, etc.) |
| `preOAuthActionVariables: [...]` | Define what to collect | Used with preOAuthActions |

---

## Tool Schema Design

### Key Principles

1. **No bearerToken in schemas** - Authentication is handled internally
2. **No contextData fields in schemas** - These are injected at runtime
3. **Rich descriptions** - LLMs use descriptions to understand tools
4. **Business context** - Explain what the tool does in business terms
5. **Validation rules** - Use `minimum`, `maximum`, `format`, `pattern`, `enum`
6. **Output schemas** - Help LLMs understand response structure

### Schema Example

```typescript
// CORRECT: Only business parameters
const createInvoiceSchema = {
  type: 'object',
  properties: {
    customerName: {
      type: 'string',
      description: 'Full name of the customer for invoice billing'
    },
    amount: {
      type: 'number',
      description: 'Invoice amount in base currency (e.g., USD)',
      minimum: 0.01
    },
    dueDate: {
      type: 'string',
      format: 'date',
      description: 'Payment due date in YYYY-MM-DD format'
    },
    lineItems: {
      type: 'array',
      description: 'List of products/services being invoiced',
      items: {
        type: 'object',
        properties: {
          description: { type: 'string', description: 'Item description' },
          quantity: { type: 'integer', description: 'Quantity of items', minimum: 1 },
          unitPrice: { type: 'number', description: 'Price per unit', minimum: 0 }
        },
        required: ['description', 'quantity', 'unitPrice']
      }
    }
  },
  required: ['customerName', 'amount', 'dueDate']
};
```

### MCP Response Format

Always use the standard MCP content array format:

```typescript
// Standard success response
return {
  content: [{
    type: "text",
    text: JSON.stringify({
      success: true,
      data: responseData,
      message: 'Operation completed successfully',
      timestamp: new Date().toISOString()
    }, null, 2)
  }]
};

// Standard error response
return {
  content: [{
    type: "text",
    text: JSON.stringify({
      success: false,
      error: 'Error description',
      errorCode: 'ERROR_CODE',
      timestamp: new Date().toISOString()
    }, null, 2)
  }]
};
```

---

## Testing & Validation

### Manual Testing

```bash
# 1. Health check
curl http://localhost:3000/health

# 2. Initialize (optional - some clients send this first)
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}'

# 3. List tools (should NOT include bearerToken in schemas)
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# 4. Call a tool (bearerToken passed in arguments, simulating Integration Hub)
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"yourservice.list_items",
      "arguments":{
        "bearerToken":"your_test_token",
        "maxResults": 5
      }
    }
  }'

# 5. Test auth endpoints (with internal API key)
curl http://localhost:3000/auth/credentials/yourservice \
  -H "X-Service-Secret: your_internal_api_key"

curl http://localhost:3000/auth/metadata/yourservice \
  -H "X-Service-Secret: your_internal_api_key"

# 6. Test post-auth
curl -X POST http://localhost:3000/auth/post-auth \
  -H "Content-Type: application/json" \
  -H "X-Service-Secret: your_internal_api_key" \
  -d '{"accessToken":"test_token","tokenResponse":{"team":{"id":"T123","name":"Test"}}}'
```

### Validation Checklist

**Core MCP:**
- [ ] `/mcp` endpoint handles `initialize`, `tools/list`, `tools/call`, `notifications/initialized`
- [ ] `tools/list` returns tools WITHOUT bearerToken in inputSchema
- [ ] `tools/call` validates bearerToken presence at runtime
- [ ] Tool handlers receive bearerToken and contextData in args
- [ ] All responses use MCP content array format
- [ ] Error responses follow JSON-RPC 2.0 format

**Auth Endpoints:**
- [ ] `/auth/credentials/:id` returns OAuth credentials from envs.ts
- [ ] `/auth/metadata/:id` returns integration metadata from envs.ts
- [ ] `/auth/post-auth` returns contextData (if postOAuthActions enabled)
- [ ] `/auth/status` returns configuration health
- [ ] All auth endpoints protected by verifyInternalService middleware

**Configuration:**
- [ ] All env variables centralized in `src/config/envs.ts`
- [ ] Service-specific prefixes used (GMAIL_, SLACK_, etc.)
- [ ] Validation function checks required variables
- [ ] CONFIG object exported for convenience

---

## Deployment & Production

### Environment Variables

```env
# Server Configuration
NODE_ENV=production
PORT=3000

# Security
INTERNAL_SERVICES_API_KEY=secure_production_key

# Service OAuth (use SERVICE_ prefix)
YOURSERVICE_CLIENT_ID=production_client_id
YOURSERVICE_CLIENT_SECRET=production_client_secret
YOURSERVICE_AUTH_URL=https://auth.yourservice.com/oauth/authorize
YOURSERVICE_TOKEN_URL=https://auth.yourservice.com/oauth/token
YOURSERVICE_REDIRECT_URI=https://yourdomain.com/auth/callback
YOURSERVICE_SCOPES=read,write

# API
YOURSERVICE_API_BASE_URL=https://api.yourservice.com/v1

# CORS
CORS_ORIGIN=https://yourdomain.com
```

### Docker Configuration

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY ../dist ./dist
COPY assets ./assets
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

---

## Best Practices Summary

### DO

1. **Direct JSON-RPC 2.0** - Handle MCP protocol methods directly, no SDK needed
2. **Centralize env vars** - All in `src/config/envs.ts` with service-specific prefixes
3. **No bearerToken in schemas** - Authentication handled internally by Integration Hub
4. **Use postOAuthActions** - When you need to extract data after OAuth (contextData)
5. **Use preOAuthActions** - When you need user input before OAuth (region, instance URL)
6. **Return contextData properly** - Items in contextData get merged and passed to all tool calls
7. **Rich tool descriptions** - LLMs use these for understanding
8. **Output schemas** - Help LLMs understand response structure
9. **Direct API calls with axios** - No vendor SDKs
10. **Square brand icons** - 32x32px SVG for integration grid display
11. **Local asset storage** - No internet dependencies for brand assets
12. **Mask sensitive data in logs** - Never log bearerToken values

### DON'T

1. **Don't use @modelcontextprotocol/sdk** - Direct implementation is simpler
2. **Don't add bearerToken to inputSchema** - It's injected internally
3. **Don't add contextData fields to inputSchema** - They're injected internally
4. **Don't use process.env directly** - Use envs.ts exports
5. **Don't hardcode OAuth credentials** - Always from environment variables
6. **Don't use vendor SDKs** - Direct HTTP with axios
7. **Don't use WebSocket** - HTTP-only architecture
8. **Don't use multiple ports** - Single Express server
9. **Don't use full logos** - Square icons only for integration grid
10. **Don't block OAuth on post-auth failure** - Return success with empty data

---

## Cursor AI Prompt

Copy and paste this prompt into Cursor AI to understand this framework:

```
You are an expert MCP (Model Context Protocol) server developer. Build MCP servers following this exact framework:

## CORE ARCHITECTURE:
- Direct JSON-RPC 2.0 implementation over HTTP (NO @modelcontextprotocol/sdk)
- Express.js with helmet, CORS, body parsing
- Single port, stateless request/response pattern
- All env vars centralized in src/config/envs.ts with SERVICE_ prefix naming

## MCP ENDPOINT PATTERN (POST /mcp):
Handle these JSON-RPC 2.0 methods via switch/case:
- "initialize" → Return protocolVersion, capabilities, serverInfo
- "tools/list" → Return tool definitions (NO bearerToken in inputSchema)
- "tools/call" → Validate bearerToken presence, find tool, execute handler
- "notifications/initialized" → Acknowledge

## CRITICAL: BEARER TOKEN HANDLING:
- bearerToken is NEVER in tool inputSchema - Integration Hub injects it at runtime
- Validate bearerToken in /mcp tools/call handler before executing
- Tool handlers receive bearerToken in args: const { bearerToken, ...params } = args;
- contextData fields from pre-oauth and post-auth are also injected into args at runtime

## AUTH ROUTES (all protected by verifyInternalService middleware):
- GET /auth/credentials/:integrationId → OAuth credentials from envs.ts
- GET /auth/metadata/:integrationId → Integration metadata from envs.ts
- POST /auth/post-auth → Post-OAuth data extraction (when postOAuthActions: true)
- GET /auth/status → Configuration health check

## POST-AUTH RESPONSE FORMAT:
{
  success: true,
  data: {
    contextData: { ... },      // MERGED with pre-OAuth data, PASSED to ALL tool calls
    accountMetadata: { ... }   // SAVED to DB only, NOT passed to tool calls
  },
  timestamp: '...'
}

## PRE-OAUTH VARIABLES (in metadata response):
preOAuthActions: true,
preOAuthActionVariables: [
  { key: 'region', label: 'Data Center', type: 'select', required: true, options: [...], default: 'com' }
]
Pre-OAuth variables are saved as contextData, merged with post-auth contextData.

## FILE STRUCTURE:
src/config/envs.ts     - ALL env vars centralized here
src/index.ts           - Express server with /mcp JSON-RPC handler
src/routes/auth.routes.ts - Integration Hub endpoints
src/middleware/auth.middleware.ts - API key protection
src/tools/*.tools.ts   - Tool definitions (NO bearerToken in schemas)
src/services/api.service.ts - Axios HTTP client

## TOOL DEFINITION PATTERN:
{
  tool: {
    name: 'service.action_name',
    description: 'Rich description for LLM understanding',
    inputSchema: { type: 'object', properties: { /* business params only */ } },
    outputSchema: { type: 'object', properties: { /* response structure */ } }
  },
  handler: async (args) => {
    const { bearerToken, ...params } = args;  // bearerToken injected at runtime
    const result = await makeApiCall('/endpoint', bearerToken, 'GET', undefined, params);
    return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
  }
}

## DEPENDENCIES (NO MCP SDK):
express, cors, helmet, dotenv, axios
Dev: typescript, @types/node, @types/express, @types/cors, ts-node, nodemon

## ANTI-PATTERNS:
- @modelcontextprotocol/sdk (not needed)
- bearerToken in tool inputSchema (handled internally)
- contextData fields in tool inputSchema (handled internally)
- process.env used directly outside envs.ts
- Vendor SDKs (use axios directly)
- WebSocket transport
- Hardcoded OAuth credentials
```

---

*This guide is based on production MCP servers including Gmail, Apollo, Slack, QuickBooks, DocuSign, Xero, and many more. All patterns are production-tested.*
