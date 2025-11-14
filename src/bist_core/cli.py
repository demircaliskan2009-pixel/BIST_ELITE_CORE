import argparse, json
from .runner import run_decision
def main():
    p = argparse.ArgumentParser()
    p.add_subparsers(dest='cmd').add_parser('ask').add_argument('question', nargs='?')
    print(json.dumps(run_decision(), ensure_ascii=False, indent=2))
if __name__ == '__main__': main()
