from collections import defaultdict


class ExpectancyTracker:
    def __init__(self):
        self.data = defaultdict(list)

    def record_trade(self, edge, pnl):
        bucket = round(edge, 1)
        self.data[bucket].append(pnl)

    def stats(self):
        result = {}
        for k, v in self.data.items():
            if not v:
                continue
            wins = [x for x in v if x > 0]
            losses = [x for x in v if x <= 0]

            winrate = len(wins) / len(v)
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            expectancy = winrate * avg_win + (1 - winrate) * avg_loss

            result[k] = {
                "winrate": winrate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "expectancy": expectancy,
                "trades": len(v)
            }

        return result


tracker = ExpectancyTracker()

__all__ = ["tracker"]
