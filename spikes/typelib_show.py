"""按名字查类型库里任意接口的完整签名（typelib_dump.py 只写了反应相关的接口）。

用法：python spikes/typelib_show.py ComponentList ComponentLists
      python spikes/typelib_show.py --grep SaveAs          只列出成员名含 SaveAs 的接口和签名
"""

import argparse

import pythoncom
from _common import use_utf8
from typelib_dump import TLB_GUID, TLB_LCID, TLB_MAJOR, TLB_MINOR, read_type

use_utf8()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    parser.add_argument("--grep", default="")
    args = parser.parse_args()
    tlb = pythoncom.LoadRegTypeLib(TLB_GUID, TLB_MAJOR, TLB_MINOR, TLB_LCID)
    wanted = set(args.names)
    for index in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(index)[0]
        if wanted and name not in wanted:
            continue
        record = read_type(tlb, index)
        if args.grep:
            hits = [text for member, text in record.members if args.grep.lower() in member.lower()]
            for text in hits:
                print(f"{name}.{text}")
            continue
        if not wanted:
            continue
        bases = f" : {', '.join(record.bases)}" if record.bases else ""
        print(f"[{record.kind}] {name}{bases}")
        for _, text in record.members:
            print(f"    {text}")


if __name__ == "__main__":
    main()
