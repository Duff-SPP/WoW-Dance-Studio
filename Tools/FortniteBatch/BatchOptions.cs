using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;

internal sealed class BatchOptions
{
    public string ReportRoot = Path.GetFullPath("report");
    public int Limit = 3;
    public string Source = "favorites";
    public string? Destination;
    public bool Export;
    public bool CatalogOnly;
    public bool Help;
    public bool SelfTest;
    public HashSet<string>? Ids;

    public static BatchOptions Parse(string[] args)
    {
        var result = new BatchOptions();
        int position = 0;
        for (int i = 0; i < args.Length; ++i)
        {
            string value = args[i];
            string Next()
            {
                if (++i >= args.Length) throw new ArgumentException("Missing value for " + value);
                return args[i];
            }
            switch (value)
            {
                case "--help": case "-h": result.Help = true; break;
                case "--self-test": result.SelfTest = true; break;
                case "--source": result.Source = Next(); break;
                case "--export": result.Export = true; break;
                case "--catalog-only": result.CatalogOnly = true; break;
                case "--destination": result.Destination = Path.GetFullPath(Next()); break;
                case "--inspect-ids": result.Ids = new HashSet<string>(Next().Split(','), StringComparer.OrdinalIgnoreCase); break;
                case "--ids-file":
                    result.Ids = new HashSet<string>(JsonConvert.DeserializeObject<List<string>>(File.ReadAllText(Next()))
                        ?? throw new ArgumentException("IDs file must contain a JSON string array."), StringComparer.OrdinalIgnoreCase);
                    if (result.Ids.Count == 0) throw new ArgumentException("IDs file is empty.");
                    break;
                default:
                    if (value.StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("Unknown option: " + value);
                    if (position++ == 0) result.ReportRoot = Path.GetFullPath(value);
                    else if (position == 2 && int.TryParse(value, out int limit) && limit > 0) result.Limit = limit;
                    else throw new ArgumentException("Expected report folder and positive maximum count.");
                    break;
            }
        }
        if (result.Source != "favorites" && result.Source != "catalog") throw new ArgumentException("Source must be favorites or catalog.");
        if (result.Export && result.CatalogOnly) throw new ArgumentException("Export and catalog-only are separate operations.");
        return result;
    }

    public static void Test()
    {
        var value = Parse(new[] {"report", "12", "--source", "catalog", "--catalog-only"});
        if (value.Limit != 12 || value.Source != "catalog" || !value.CatalogOnly) throw new Exception("Catalog options failed.");
        var legacy = Parse(new[] {"report", "3", "--inspect-ids", "EID_One,EID_Two"});
        if (legacy.Ids is null || !legacy.Ids.Contains("eid_one") || legacy.Source != "favorites") throw new Exception("Legacy arguments failed.");
        foreach (var invalid in new[] {new[]{"report","0"}, new[]{"--source","unknown"}, new[]{"--ids-file"}, new[]{"--unknown"}})
        {
            bool rejected = false;
            try { Parse(invalid); } catch (ArgumentException) { rejected = true; }
            if (!rejected) throw new Exception("Invalid arguments accepted.");
        }
        Console.WriteLine("PASS: catalog, legacy, and invalid option cases (no parser initialized).");
    }
}
