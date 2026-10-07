import csv
p='vendor/ffxiv-datamining/csv/en/Item.csv'
with open(p,encoding='utf-8') as f:
    reader=csv.reader(f)
    header=next(reader)
    # print first 60 header fields for inspection
    print('header sample (first 120):')
    for i,h in enumerate(header[:120], start=0):
        print(i, h)
    cols=['LevelItem','ItemSearchCategory','ItemUICategory','FilterGroup','EquipSlotCategory','Rarity','Icon']
    idxs={c: header.index(c) if c in header else None for c in cols}
    print('\nindices:', idxs)
    # find row 4839
    for row in reader:
        if row and row[0]=='4839':
            print('\nrow4839 sample cols:')
            for c in cols:
                i=idxs[c]
                print(c, row[i] if i is not None and i < len(row) else None)
            break
