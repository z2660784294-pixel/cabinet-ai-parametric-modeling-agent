// src/types/index.ts
import { Socket } from 'net';
import { Context as MCPContext } from 'fastmcp';

export interface KoomasterCommandParams {
  [key: string]: any;
}

export interface KoomasterConnectionOptions {
  host: string;
  port: number;
  sock?: Socket;
}

export interface KoomasterResponse {
  status: string;
  message?: string;
  result?: any;
}

// 使用 FastMCP 的会话认证类型
export type SessionAuth = undefined;

// 扩展 FastMCP 的 Context 类型
export type Context = MCPContext<SessionAuth>;