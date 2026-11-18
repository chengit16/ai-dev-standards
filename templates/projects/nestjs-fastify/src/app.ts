/** @description 装配 NestJS 与 Fastify，健康端点独立于外部服务。 */
import "reflect-metadata";
import { Controller, Get, Module } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import {
  FastifyAdapter,
  type NestFastifyApplication,
} from "@nestjs/platform-fastify";

@Controller("api")
class HealthController {
  /** 返回稳定的 HTTP 健康响应，不依赖数据库。 */
  @Get("health")
  health(): { status: "ok" } {
    return { status: "ok" };
  }
}

@Module({ controllers: [HealthController] })
class AppModule {}

/** 构造使用真实 Fastify 适配器的应用，调用方负责启动及关闭。 */
export function createApp(): Promise<NestFastifyApplication> {
  return NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter(),
    { logger: ["error"] },
  );
}
