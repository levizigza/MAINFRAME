import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { DEFAULT_POLICY, assertPolicySafe } from "./policy.js";
import { loadOrCreateLoopbackToken } from "./db.js";

export type LoopbackServer = {
  port: number;
  token: string;
  url: string;
  close: () => Promise<void>;
};

/**
 * Bind FreeForge HTTP status listener to loopback with bearer auth.
 * Does not enable outbound delivery or background model calls.
 */
export function startLoopbackStatusServer(
  getStatus: () => Promise<unknown> | unknown,
  port = 18791,
): Promise<LoopbackServer> {
  assertPolicySafe(DEFAULT_POLICY);
  const token = loadOrCreateLoopbackToken();
  const host = DEFAULT_POLICY.bindAddress;

  return new Promise((resolve, reject) => {
    const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
      const auth = req.headers.authorization || "";
      const ok =
        auth === `Bearer ${token}` ||
        req.headers["x-freeforge-token"] === token;
      if (!ok) {
        res.writeHead(401, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "unauthorized" }));
        return;
      }
      if (req.method === "GET" && (req.url === "/" || req.url === "/status")) {
        try {
          const body = await getStatus();
          res.writeHead(200, { "content-type": "application/json" });
          res.end(JSON.stringify(body, null, 2));
        } catch (err) {
          res.writeHead(500, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: String(err) }));
        }
        return;
      }
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "not_found" }));
    });

    server.once("error", reject);
    server.listen(port, host, () => {
      resolve({
        port,
        token,
        url: `http://${host}:${port}/status`,
        close: () =>
          new Promise((resClose, rejClose) => {
            server.close((err) => (err ? rejClose(err) : resClose()));
          }),
      });
    });
  });
}
