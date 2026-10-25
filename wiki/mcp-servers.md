# Recommended MCP Servers for VoiceLive API DriveThru Agent Demo

This document outlines the Model Context Protocol (MCP) servers that would be beneficial for developing this project, sourced from the [Awesome GitHub Copilot](https://github.github.io/awesome-copilot/llms.txt) repository.

## What are MCP Servers?

MCP (Model Context Protocol) servers provide tools and context that AI agents can use to interact with external systems, APIs, and data sources. They enable your agent to:
- Access real-time data
- Execute operations
- Integrate with existing tools and services

## Essential MCP Servers for This Project

### 1. **Azure MCP Server** ⭐ Priority
**Use Case**: Interact with Azure resources (Foundry, AI Services, databases)

**Relevant Agents/Skills:**
- [Azure Resource Visualizer](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/azure-resource-visualizer/SKILL.md) - Visualize Azure resource architecture
- [Azure Deployment Preflight](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/azure-deployment-preflight/SKILL.md) - Validate deployments before running
- [Kusto Assistant](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/kusto-assistant.agent.md) - Query Azure Data Explorer

**Why**: Essential for managing Azure Foundry resources, monitoring agent performance, and querying logs.

### 2. **Microsoft Agent Framework (Python)** ⭐ Priority
**Use Case**: Build and deploy agents using Microsoft's Agent Framework

**Relevant Resources:**
- [Microsoft Agent Framework Python](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/microsoft-agent-framework-python.agent.md)
- [Agent Workflow Builder AI Toolkit](https://github.com/microsoft/windows-ai-studio)
- [Microsoft Docs](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/microsoft-docs/SKILL.md) - Query official Microsoft documentation

**Why**: Your project uses Azure Foundry agents which are built on Microsoft Agent Framework.

### 3. **Database MCP Servers** ⭐ Priority (Future)
**Use Case**: Manage transactional order database

**Options:**
- **PostgreSQL MCP**: [PostgreSQL DBA](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/postgresql-dba.agent.md)
- **MS SQL MCP**: [MS SQL DBA](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/ms-sql-dba.agent.md)
- **MongoDB MCP**: [MongoDB Performance Advisor](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/mongodb-performance-advisor.agent.md)

**Why**: For the transactional database that will store orders (planned feature).

### 4. **GitHub MCP Server**
**Use Case**: Repository management, issues, PRs, and CI/CD

**Relevant Resources:**
- [GitHub Issues](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/github-issues/SKILL.md)
- [GitHub Actions Expert](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/github-actions-expert.agent.md)

**Why**: Manage project development workflow, create issues for bugs/features.

### 5. **Playwright MCP Server**
**Use Case**: Test the React/TypeScript frontend

**Relevant Resources:**
- [Playwright TypeScript](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/playwright-typescript.instructions.md)
- [Playwright Tester Mode](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/playwright-tester.agent.md)

**Why**: Automated testing of the DriveThru UI and voice interactions.

## MCP Servers for Enhanced Development

### 6. **Filesystem MCP Server**
**Use Case**: File operations, reading/writing configuration

**Why**: Manage project files, configuration files, and generated code.

### 7. **Power BI MCP Server** (Future - Data Analytics)
**Use Case**: Create dashboards and analytics for order data

**Relevant Resources:**
- [Power BI Data Modeling Expert](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/power-bi-data-modeling-expert.agent.md)
- [Power BI DAX Expert](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/power-bi-dax-expert.agent.md)

**Why**: For the planned Fabric Data Agent that will provide analytics on orders.

### 8. **Browser Automation MCP (Chrome DevTools)**
**Use Case**: Debug and test the web frontend

**Relevant Resources:**
- [Chrome DevTools](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/chrome-devtools/SKILL.md)
- [Web Design Reviewer](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/web-design-reviewer/SKILL.md)

**Why**: Visual inspection and debugging of the React UI.

### 9. **REST API Testing MCP**
**Use Case**: Test VoiceLive API integration

**Why**: Validate agent responses and API interactions.

### 10. **Python Testing MCP Server**
**Use Case**: Run and validate Python test scripts

**Why**: Validate agent tools and conversation flows with automated tests.

## GitHub Copilot Custom Agents to Use

### Agent Development

1. **[API Architect](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/api-architect.agent.md)**
   - Design the agent's API structure and tools

2. **[Azure Principal Architect](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/azure-principal-architect.agent.md)**
   - Azure Well-Architected Framework guidance

3. **[Software Engineer Agent](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/software-engineer-agent-v1.agent.md)**
   - Production-ready code development

### Frontend Development

4. **[Expert React Frontend Engineer](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/expert-react-frontend-engineer.agent.md)**
   - React 19+ best practices

5. **[TypeScript MCP Server Expert](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/typescript-mcp-expert.agent.md)**
   - TypeScript development patterns

### Testing & Quality

6. **[Polyglot Test Generator](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/polyglot-test-generator.agent.md)**
   - Generate comprehensive test suites

7. **[Accessibility Expert](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/accessibility.agent.md)**
   - Ensure DriveThru is accessible (important for voice UI)

### DevOps

8. **[DevOps Expert](https://raw.githubusercontent.com/github/awesome-copilot/main/agents/devops-expert.agent.md)**
   - CI/CD pipeline setup

9. **[Azure DevOps CLI](https://raw.githubusercontent.com/github/awesome-copilot/main/skills/azure-devops-cli/SKILL.md)**
   - Manage Azure DevOps resources

## GitHub Copilot Instructions to Apply

### Python Development
- [Python](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/python.instructions.md)
- [Python MCP Server](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/python-mcp-server.instructions.md)

### TypeScript/React Development
- [TypeScript 5 ES2022](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/typescript-5-es2022.instructions.md)
- [ReactJS](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/reactjs.instructions.md)

### Azure & Cloud
- [Azure Foundry](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/azure-verified-modules-bicep.instructions.md)
- [Bicep Best Practices](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/bicep-code-best-practices.instructions.md)

### Testing
- [Playwright TypeScript](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/playwright-typescript.instructions.md)

### General Best Practices
- [Security and OWASP](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/security-and-owasp.instructions.md)
- [Performance Optimization](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/performance-optimization.instructions.md)
- [Accessibility (A11y)](https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/a11y.instructions.md)

## How to Install and Use MCP Servers

### 1. Install MCP CLI (if available)

```powershell
# Check if npx is available
npx mcp --version

# Or install globally
npm install -g @modelcontextprotocol/cli
```

### 2. Configure GitHub Copilot for MCP

Add MCP server configurations to your VS Code settings or project:

```json
{
  "github.copilot.mcp.servers": [
    {
      "name": "azure-mcp",
      "command": "npx",
      "args": ["@azure/mcp-server"]
    },
    {
      "name": "github-mcp",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-github"]
    }
  ]
}
```

### 3. Use Custom Agents

Download and place custom agents in your `.github/copilot` folder:

```powershell
# Create folder structure
mkdir -p .github/copilot/agents

# Download an agent (example)
curl -o .github/copilot/agents/azure-architect.agent.md `
  https://raw.githubusercontent.com/github/awesome-copilot/main/agents/azure-principal-architect.agent.md
```

### 4. Apply Instructions

Download and use instruction files:

```powershell
mkdir -p .github/copilot/instructions

# Download instructions
curl -o .github/copilot/instructions/python.instructions.md `
  https://raw.githubusercontent.com/github/awesome-copilot/main/instructions/python.instructions.md
```

## Priority Implementation Plan

### Phase 1: Foundation (Current)
1. ✅ Azure MCP Server
2. ✅ Microsoft Agent Framework resources
3. ✅ GitHub MCP Server
4. ✅ Filesystem MCP Server

### Phase 2: Frontend Development
1. React/TypeScript development agents
2. Playwright for testing
3. Browser automation tools

### Phase 3: Database Integration (Future)
1. Database MCP server (PostgreSQL/SQL Server)
2. Database schema agents

### Phase 4: Analytics Integration (Future)
1. Power BI MCP Server
2. Fabric workspace tools
3. Data analytics agents

## Learning Resources

- [Awesome GitHub Copilot Repository](https://github.com/github/awesome-copilot)
- [Model Context Protocol Documentation](https://modelcontextprotocol.io)
- [Azure AI Foundry Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/)
- [Microsoft Agent Framework](https://learn.microsoft.com/en-us/azure/ai-services/agents/)

## Contributing

As you discover useful MCP servers or agents for this project, document them here! Consider:
- Adding specific configuration examples
- Documenting integration patterns
- Sharing lessons learned
- Contributing back to awesome-copilot repository
