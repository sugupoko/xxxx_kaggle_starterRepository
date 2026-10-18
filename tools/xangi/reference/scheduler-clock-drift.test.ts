import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

// node-cron を差し替えて「どんなオプションで登録されたか」「タイマーを張り直しているか」を見る。
// 実時計に依存すると 15 分待つテストになってしまうので、fake timer で回す。
const cronTask = {
  getNextRun: vi.fn<() => Date | null>(() => null),
  start: vi.fn(),
  stop: vi.fn(),
};
const cronSchedule = vi.fn(() => cronTask);
vi.mock('node-cron', () => ({
  default: {
    schedule: (...args: unknown[]) => cronSchedule(...(args as [])),
    validate: () => true,
  },
}));

const { Scheduler } = await import('../src/scheduler.js');
type Sched = InstanceType<typeof Scheduler>;

function makeScheduler(): Sched {
  return new Scheduler(mkdtempSync(join(tmpdir(), 'xangi-drift-test-')), { quiet: true });
}

function startCronJob(scheduler: Sched): void {
  (scheduler as unknown as { startJob(s: unknown): void }).startJob({
    id: 'job1',
    type: 'cron',
    expression: '0,30 7-12 * * *',
    message: 'テストジョブ',
    channelId: 'ch1',
    platform: 'discord',
    createdAt: new Date().toISOString(),
    enabled: true,
  });
}

describe('Scheduler 壁時計ジャンプ対策', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    cronTask.getNextRun.mockReturnValue(null);
    cronTask.start.mockClear();
    cronTask.stop.mockClear();
    cronSchedule.mockClear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('遅刻許容量を広げて cron を登録する（既定 1 秒だと WSL2 では全スロットが捨てられる）', () => {
    const scheduler = makeScheduler();
    startCronJob(scheduler);

    const options = cronSchedule.mock.calls[0][2] as {
      timezone: string;
      missedExecutionTolerance: number;
    };
    expect(options.timezone).toBe('Asia/Tokyo');
    expect(options.missedExecutionTolerance).toBeGreaterThanOrEqual(60_000);
    scheduler.stopAll();
  });

  it('発火まで間があるジョブはタイマーを張り直す', () => {
    const scheduler = makeScheduler();
    startCronJob(scheduler);
    cronTask.getNextRun.mockReturnValue(new Date(Date.now() + 10 * 60_000));

    vi.advanceTimersByTime(31_000);

    expect(cronTask.stop).toHaveBeenCalled();
    expect(cronTask.start).toHaveBeenCalled();
    scheduler.stopAll();
  });

  it('発火直前のジョブには触らない（張り直すとそのスロットを取りこぼす）', () => {
    const scheduler = makeScheduler();
    startCronJob(scheduler);
    cronTask.getNextRun.mockReturnValue(new Date(Date.now() + 30_000));

    vi.advanceTimersByTime(31_000);

    expect(cronTask.stop).not.toHaveBeenCalled();
    expect(cronTask.start).not.toHaveBeenCalled();
    scheduler.stopAll();
  });

  it('cron ジョブが無くなったら張り直しループも止まる', () => {
    const scheduler = makeScheduler();
    startCronJob(scheduler);
    cronTask.getNextRun.mockReturnValue(new Date(Date.now() + 10 * 60_000));

    scheduler.stopAll();
    vi.advanceTimersByTime(120_000);

    expect(cronTask.start).not.toHaveBeenCalled();
  });
});
