// Ambient 声明：让 tsc 在未安装 better-sqlite3 的环境（如沙箱）也能通过类型检查。
// 真实运行时由主机 `npm install`（package.json 已登记依赖）编译本机原生二进制。
// 仅 /api/positions 路由用到 better-sqlite3 直读 runtime.db（canonical 持仓）。
declare module 'better-sqlite3'
