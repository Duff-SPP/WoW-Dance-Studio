using System;
using System.IO;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Security.Cryptography;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.Animation;
using CUE4Parse.UE4.Assets.Objects;
using CUE4Parse.UE4.Objects.Core.i18N;
using CUE4Parse.UE4.Objects.UObject;
using FortnitePorting.Application;
using FortnitePorting;
using FortnitePorting.Exporting;
using FortnitePorting.Exporting.Context;
using FortnitePorting.Exporting.Types;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using CUE4Parse_Conversion.Options;
using CUE4Parse_Conversion.Writers.UEFormat.Enums;

[assembly: System.Reflection.AssemblyInformationalVersion("4.3.4")]

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            var options = BatchOptions.Parse(args);
            if (options.Help)
            {
                Console.WriteLine("Batch <report-folder> <maximum> [--source favorites|catalog] [--catalog-only | --export] [--ids-file file.json] [--destination folder]");
                Console.WriteLine("Catalog reads the current AthenaDanceItemDefinition registry. No parser starts for --help or --self-test.");
                return 0;
            }
            if (options.SelfTest)
            {
                BatchOptions.Test();
                var tags = new HashSet<string>(StringComparer.Ordinal);
                ReadTags(JToken.Parse("{\"nested\":[\"Cosmetics.Test.Tag\",\"other\",{\"tag\":\"Cosmetics.Test.Tag\"}]}"), tags);
                if (tags.Count != 1 || !tags.Contains("Cosmetics.Test.Tag")) throw new Exception("Metadata tag extraction failed.");
                Console.WriteLine("PASS: recursive metadata tag extraction and duplicate handling.");
                return 0;
            }
            Console.WriteLine("Initializing existing Fortnite Porting services (no settings writes).");
            AppServices.Initialize();
            AppServices.AppSettings.Load();
            AppServices.AppSettings.ShouldSaveOnExit = false;
            // Keep the user's existing cache intact during this separate inspection session.
            AppServices.AppSettings.Developer.ChunkCacheLifetime = int.MaxValue / 100000;
            Console.WriteLine("Assets: " + AppServices.App.AssetsFolder.FullName);
            var parser = AppServices.UEParse;
            parser.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName == "Status" && !parser.Status.StartsWith("Loading ")
                    && !parser.Status.StartsWith("Registering ")) Console.WriteLine(parser.Status);
            };
            await parser.Initialize();
            Console.WriteLine("Parser initialized: " + parser.FinishedLoading);
            Console.WriteLine("Files: " + parser.Provider?.Files.Count);
            var provider = parser.Provider;
            if (!parser.FinishedLoading || provider is null) return 1;
            var reportRoot = options.ReportRoot;
            var limit = options.Limit;
            Directory.CreateDirectory(Path.Combine(reportRoot, "assets"));
            var available = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var candidates = new List<string>();
            if (options.Source == "catalog")
            {
                foreach (var data in parser.AssetRegistry)
                    if (data.AssetClass.Text == "AthenaDanceItemDefinition" && available.Add(data.ObjectPath)) candidates.Add(data.ObjectPath);
            }
            else
            {
                foreach (var path in AppServices.AppSettings.Application.FavoriteAssets)
                    if (path.Contains("/Dances/", StringComparison.OrdinalIgnoreCase) && available.Add(path)) candidates.Add(path);
            }
            if (options.Export) return await ExportSelected(reportRoot, limit, options, available);
            if (options.Source == "catalog") candidates.Sort(StringComparer.OrdinalIgnoreCase);
            var catalog = new List<CatalogEntry>();
            var rows = new List<EmoteAudit>();
            var identifiers = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            WriteJson(Path.Combine(reportRoot, "audit-source.json"), new { Source = options.Source });
            if (options.CatalogOnly)
            {
                WriteJson(Path.Combine(reportRoot, "catalog.json"), catalog);
                WriteJson(Path.Combine(reportRoot, "catalog-info.json"), new { Source=options.Source, Available=available.Count, Attempted=0, Complete=false });
            }
            else WriteJson(Path.Combine(reportRoot, "audit.json"), rows);
            foreach (var path in candidates)
            {
                var identifier = path[(path.LastIndexOf('.') + 1)..];
                if (options.Ids is not null && !options.Ids.Contains(identifier)) continue;
                if (catalog.Count >= limit) break;
                if (!identifiers.Add(identifier)) throw new InvalidDataException("Ambiguous duplicate emote identifier: " + identifier);
                var row = new EmoteAudit { AssetPath = path, Id = path[(path.LastIndexOf('.') + 1)..] };
                var entry = new CatalogEntry { Id = row.Id, AssetPath = path };
                catalog.Add(entry);
                try
                {
                    var asset = provider.LoadPackageObject(path);
                    if (asset is null) throw new InvalidDataException("Emote asset could not be loaded.");
                    row.Name = (asset.GetOrDefault<FText?>("DisplayName")
                        ?? asset.GetOrDefault<FText?>("ItemName"))?.Text ?? row.Id;
                    entry.Name = row.Name;
                    var serialized = JsonConvert.SerializeObject(asset, Formatting.Indented);
                    var properties = JObject.Parse(serialized)["Properties"];
                    var tags = new HashSet<string>(StringComparer.Ordinal);
                    ReadTags(properties?["DataList"], tags);
                    ReadTags(properties?["GameplayTags"], tags);
                    entry.Tags.AddRange(tags);
                    entry.Tags.Sort(StringComparer.Ordinal);
                    entry.Status = "inspected";
                    if (options.CatalogOnly) continue;
                    rows.Add(row);
                    row.AssetJson = Path.Combine(reportRoot, "assets", row.Id + ".json");
                    File.WriteAllText(row.AssetJson, serialized);
                    AddVariant(row, "Male Medium", asset.GetOrDefault<UAnimMontage?>("Animation")
                        ?? asset.GetOrDefault<UAnimMontage?>("FrontEndAnimation"));
                    AddVariant(row, "Female Medium", asset.GetOrDefault<UAnimMontage?>("AnimationFemaleOverride"));
                    var overrides = asset.GetOrDefault<FStructFallback[]>("AnimationOverrides", Array.Empty<FStructFallback>());
                    foreach (var item in overrides)
                    {
                        var gender = item.GetOrDefault<FName>("Gender").Text;
                        var body = item.GetOrDefault<FName>("BodyType").Text;
                        row.OverrideLabels.Add(gender + " " + body);
                        if (body.EndsWith("::Medium", StringComparison.Ordinal)
                            || body.EndsWith("::MediumAndSmall", StringComparison.Ordinal))
                        {
                            var overrideMontage = item.GetOrDefault<UAnimMontage?>("EmoteMontage");
                            if (gender.EndsWith("::Male", StringComparison.Ordinal))
                                AddVariant(row, "Male Medium", overrideMontage);
                            else if (gender.EndsWith("::Female", StringComparison.Ordinal))
                                AddVariant(row, "Female Medium", overrideMontage);
                            else row.Errors.Add("Medium override with unsupported gender: " + gender);
                        }
                    }
                    row.Status = row.Variants.Count == 0 ? "unresolved" : "inspected";
                }
                catch (Exception error)
                {
                    row.Status = "unresolved";
                    row.Errors.Add(error.GetType().Name + ": " + error.Message);
                    entry.Status = "unresolved";
                    entry.Error = error.GetType().Name + ": " + error.Message;
                    if (!options.CatalogOnly && !rows.Contains(row)) rows.Add(row);
                }
                finally
                {
                    if (options.CatalogOnly && catalog.Count % 25 == 0) WriteJson(Path.Combine(reportRoot, "catalog.json"), catalog);
                    else if (!options.CatalogOnly) WriteJson(Path.Combine(reportRoot, "audit.json"), rows);
                    Console.WriteLine($"[{catalog.Count}] {row.Id}: {entry.Status}");
                }
            }
            if (options.CatalogOnly)
            {
                WriteJson(Path.Combine(reportRoot, "catalog.json"), catalog);
                WriteJson(Path.Combine(reportRoot, "catalog-info.json"), new { Source=options.Source, Available=available.Count, Attempted=catalog.Count, Complete=catalog.Count==available.Count });
            }
            Console.WriteLine($"Catalog source: {options.Source}; available={available.Count}; inspected={catalog.Count}.");
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.ToString());
            return 1;
        }
    }

    private static void ReadTags(JToken? value, HashSet<string> tags)
    {
        if (value is null) return;
        if (value.Type == JTokenType.String)
        {
            var tag = (string?)value;
            if (tag is not null && tag.StartsWith("Cosmetics.", StringComparison.Ordinal)) tags.Add(tag);
            return;
        }
        foreach (var child in value.Children()) ReadTags(child, tags);
    }

    private static bool SameEvidence(Dictionary<string,string> first, Dictionary<string,string> second)
    {
        if (first.Count != second.Count) return false;
        foreach (var pair in first)
            if (!second.TryGetValue(pair.Key, out var value) || value != pair.Value) return false;
        return true;
    }

    private static void WriteJson(string path, object value)
    {
        File.WriteAllText(path + ".tmp", JsonConvert.SerializeObject(value, Formatting.Indented));
        File.Move(path + ".tmp", path, true);
    }

    private static async Task<int> ExportSelected(string root, int limit, BatchOptions options, HashSet<string> available)
    {
        var selection = JsonConvert.DeserializeObject<BatchSelection>(File.ReadAllText(Path.Combine(root, "selection.json")));
        if (selection is null || selection.SourceRevision != "8058810ece4405bfde931d97c72467b07034a881")
            throw new InvalidDataException("Selection source revision does not match this helper.");
        if (selection.AuditSha256 != HashFile(Path.Combine(root, "audit.json")))
            throw new InvalidDataException("The audit changed after classification.");
        if (selection.Source != options.Source) throw new InvalidDataException("Selection source differs from the requested source.");
        var provider = AppServices.UEParse.Provider;
        if (provider is null) throw new InvalidOperationException("No parser provider.");
        var destination = options.Destination ?? AppServices.App.AssetsFolder.FullName;
        var stage = Path.Combine(root, "staging");
        Directory.CreateDirectory(stage);
        var recordsPath = Path.Combine(root, "exports.json");
        var records = File.Exists(recordsPath)
            ? JsonConvert.DeserializeObject<List<ExportRecord>>(File.ReadAllText(recordsPath)) ?? new List<ExportRecord>()
            : new List<ExportRecord>();
        var processed = 0;
        var failed = 0;
        foreach (var item in selection.Items)
        {
            if (item.Status != "ready") continue;
            if (processed >= limit) break;
            processed++;
            var record = new ExportRecord { Id = item.Id, Name = item.Name };
            try
            {
                if (!available.Contains(item.AssetPath)) throw new InvalidDataException("Emote is no longer available in the selected source.");
                if (item.Variants.Count != 2) throw new InvalidDataException("A medium pair is required.");
                if (item.AssetSha256 != HashFile(Path.Combine(root, "assets", item.Id + ".json")))
                    throw new InvalidDataException("Asset evidence changed after classification.");
                var asset = provider.LoadPackageObject(item.AssetPath);
                if (asset is null) throw new InvalidDataException("Emote asset missing.");
                var currentJson = JsonConvert.SerializeObject(asset, Formatting.Indented);
                var currentHash = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(currentJson))).ToLowerInvariant();
                if (currentHash != item.AssetSha256) throw new InvalidDataException("Live emote metadata differs from the audit.");
                using var meta = AppServices.AppSettings.ExportSettings.CreateExportMeta(EExportLocation.AssetsFolder);
                meta.AssetsRoot = stage;
                meta.CustomPath = null;
                meta.Settings.OpenFoldersOnExport = false;
                meta.Settings.MeshFormat = EMeshFormat.UEFormat;
                meta.Settings.SoundFormat = ESoundFormat.WAV;
                meta.Settings.CompressionFormat = EFileCompressionFormat.ZSTD;
                foreach (var variant in item.Variants)
                {
                    var currentMontage = variant.Label switch
                    {
                        "Male Medium" => asset.GetOrDefault<UAnimMontage?>("Animation")
                            ?? asset.GetOrDefault<UAnimMontage?>("FrontEndAnimation"),
                        "Female Medium" => asset.GetOrDefault<UAnimMontage?>("AnimationFemaleOverride"),
                        _ => throw new InvalidDataException("Non-medium variant in selection.")
                    };
                    if (currentMontage is null || currentMontage.GetPathName() != variant.MontagePath)
                        throw new InvalidDataException("Medium montage changed or is unavailable: " + variant.Label);
                    var fresh = new VariantAudit { Label = variant.Label, MontagePath = variant.MontagePath };
                    InspectAnimation(currentMontage, fresh, new HashSet<string>(StringComparer.OrdinalIgnoreCase));
                    if (fresh.Errors.Count > 0 || fresh.PropEvidence.Count > 0)
                        throw new InvalidDataException("Animation no longer passes the prop audit.");
                    if (!new HashSet<string>(fresh.AnimationPaths, StringComparer.OrdinalIgnoreCase).SetEquals(variant.AnimationPaths))
                        throw new InvalidDataException("Animation graph changed after inspection.");
                    if (!SameEvidence(fresh.AnimationGraphs, variant.AnimationGraphs) || !SameEvidence(fresh.SequenceEvidence, variant.SequenceEvidence)
                        || !new HashSet<string>(fresh.NotifyTypes, StringComparer.Ordinal).SetEquals(variant.NotifyTypes)
                        || !new HashSet<string>(fresh.NamedNotifies, StringComparer.Ordinal).SetEquals(variant.NamedNotifies))
                        throw new InvalidDataException("Animation timing/notify evidence changed after inspection. Re-audit this selection.");
                    var export = new AnimExport(item.Name, currentMontage, [], EExportType.Animation, meta, null);
                    await export.WaitForExports();
                    if (export.Props.Count > 0) throw new InvalidDataException("Exporter discovered a prop.");
                    var context = new ExportContext(meta);
                    if (currentMontage.Skeleton is not { } skeletonReference) throw new InvalidDataException("Missing source skeleton reference.");
                    var skeleton = skeletonReference.Load<USkeleton>();
                    if (skeleton is null) throw new InvalidDataException("Unresolved source skeleton.");
                    var skeletonPath = await context.ExportAsync(skeleton, returnRealPath: true);
                    foreach (var path in variant.AnimationPaths)
                    {
                        if (provider.LoadPackageObject(path) is not UAnimSequence sequence) continue;
                        await context.ExportAsync(sequence);
                    }
                    await Task.WhenAll(context.ExportTasks);
                    var variantRecord = new VariantExportRecord { Label = variant.Label, Montage = variant.MontagePath };
                    record.Variants.Add(variantRecord);
                    variantRecord.Files.Add(Publish(skeletonPath, stage, destination, "skeleton"));
                    foreach (var path in variant.AnimationPaths)
                    {
                        if (provider.LoadPackageObject(path) is not UAnimSequence sequence) continue;
                        var stagedPath = context.GetExportPath(sequence, "ueanim");
                        variantRecord.Files.Add(Publish(stagedPath, stage, destination, "animation"));
                    }
                    foreach (var sound in export.Sounds)
                    {
                        var soundAsset = provider.LoadPackageObject(sound.Path);
                        if (soundAsset is null) throw new InvalidDataException("Exported soundtrack reference missing.");
                        var stagedPath = context.GetExportPath(soundAsset, "wav");
                        variantRecord.Files.Add(Publish(stagedPath, stage, destination, "audio"));
                    }
                    variantRecord.AudioReferences = export.Sounds.Count;
                    if (variantRecord.Files.Count == 0) throw new InvalidDataException("No animation files were produced.");
                }
                record.Status = "complete";
            }
            catch (Exception error)
            {
                record.Status = "failed";
                failed++;
                record.Error = error.GetType().Name + ": " + error.Message;
            }
            records.RemoveAll(previous => previous.Id == record.Id);
            records.Add(record);
            WriteJson(recordsPath, records);
            Console.WriteLine($"EXPORT [{processed}] {record.Name}: {record.Status} {record.Error}");
        }
        if (processed == 0) throw new InvalidDataException("No ready emotes selected. Review classification first.");
        return failed == 0 ? 0 : 1;
    }

    private static ExportedFile Publish(string staged, string stageRoot, string destination, string kind)
    {
        var info = new FileInfo(staged);
        if (!info.Exists || info.Length < (kind == "audio" ? 44 : 16))
            throw new InvalidDataException("Export failed to produce a valid-sized " + kind + " file: " + staged);
        if (kind == "animation" || kind == "skeleton")
        {
            using var stream = info.OpenRead();
            Span<byte> magic = stackalloc byte[8];
            if (stream.Read(magic) != 8 || !magic.SequenceEqual("UEFORMAT"u8))
                throw new InvalidDataException("Invalid UEFormat animation: " + staged);
        }
        var relative = Path.GetRelativePath(stageRoot, staged);
        if (relative.StartsWith("..") || Path.IsPathRooted(relative)) throw new InvalidDataException("Export path escaped staging.");
        var final = Path.Combine(destination, relative);
        var hash = HashFile(staged);
        var reused = File.Exists(final);
        if (reused && HashFile(final) != hash)
            throw new IOException("Existing file differs; preserved both copies: " + final);
        if (!reused)
        {
            var parent = Path.GetDirectoryName(final);
            if (parent is null) throw new InvalidDataException("Missing output directory.");
            Directory.CreateDirectory(parent);
            var temporary = final + ".batch-tmp";
            File.Copy(staged, temporary, true);
            File.Move(temporary, final, false);
        }
        return new ExportedFile { Kind = kind, Path = final, Sha256 = hash, Bytes = info.Length, Reused = reused };
    }

    private static string HashFile(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static void AddVariant(EmoteAudit row, string label, UAnimMontage? montage)
    {
        if (montage is null) return;
        foreach (var existing in row.Variants)
        {
            if (existing.Label != label) continue;
            if (existing.MontagePath != montage.GetPathName())
                row.Errors.Add("Conflicting medium montage references for " + label);
            return;
        }
        var variant = new VariantAudit { Label = label, MontagePath = montage.GetPathName() };
        row.Variants.Add(variant);
        var visited = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        InspectAnimation(montage, variant, visited);
    }

    private static void InspectAnimation(UAnimSequenceBase animation, VariantAudit result, HashSet<string> visited)
    {
        var path = animation.GetPathName();
        if (!visited.Add(path)) return;
        result.AnimationPaths.Add(path);
        // A list of sequence paths cannot reconstruct montage timing or routing.
        // Preserve parser evidence without interpreting section names as playback order.
        if (animation is UAnimMontage || animation is UAnimComposite)
            result.AnimationGraphs[path] = JsonConvert.SerializeObject(animation, Formatting.None);
        else if (animation is UAnimSequence)
            result.SequenceEvidence[path] = JsonConvert.SerializeObject(animation, Formatting.None);
        if (animation.Notifies is { } notifies)
        {
            foreach (var notify in notifies)
            {
                if (notify is null) { result.Errors.Add("Null notify: " + path); continue; }
                InspectNotify(notify.NotifyStateClass, result, path);
                InspectNotify(notify.Notify, result, path);
                if (notify.NotifyName is { } name && !name.IsNone) result.NamedNotifies.Add(name.Text);
            }
        }
        if (animation is UAnimMontage montage)
        {
            foreach (var slot in montage.SlotAnimTracks)
            {
                if (slot?.AnimTrack?.AnimSegments is not { } segments)
                { result.Errors.Add("Missing montage track: " + path); continue; }
                InspectSegments(segments, result, visited);
            }
            foreach (var section in montage.CompositeSections)
            {
                if (section?.LinkedSequence is not { IsNull: false } reference) continue;
                var linked = reference.Load<UAnimSequenceBase>();
                if (linked is null) result.Errors.Add("Unresolved section sequence: " + path);
                else InspectAnimation(linked, result, visited);
            }
        }
        else if (animation is UAnimComposite composite)
        {
            if (composite.AnimationTrack?.AnimSegments is not { } segments)
                result.Errors.Add("Missing composite track: " + path);
            else InspectSegments(segments, result, visited);
        }
        else if (animation is not UAnimSequence)
            result.Errors.Add("Unsupported animation type: " + animation.ExportType);
    }

    private static void InspectSegments(FAnimSegment[] segments, VariantAudit result, HashSet<string> visited)
    {
        foreach (var segment in segments)
        {
            var reference = segment?.AnimReference;
            if (reference is null || reference.IsNull)
            { result.Errors.Add("Missing animation segment reference"); continue; }
            var linked = reference.Load<UAnimSequenceBase>();
            if (linked is null) result.Errors.Add("Unresolved animation segment");
            else InspectAnimation(linked, result, visited);
        }
    }

    private static void InspectNotify(FPackageIndex? reference, VariantAudit result, string animationPath)
    {
        if (reference is null || reference.IsNull) return;
        var notify = reference.Load();
        if (notify is null) { result.Errors.Add("Unresolved notify: " + animationPath); return; }
        var type = notify.ExportType;
        if (!result.NotifyTypes.Contains(type)) result.NotifyTypes.Add(type);
        if (type.Contains("Prop", StringComparison.OrdinalIgnoreCase))
            result.PropEvidence.Add(type + ": " + notify.GetPathName());
        result.NotifyDetails.Add(JsonConvert.SerializeObject(notify, Formatting.None));
    }
}

internal sealed class EmoteAudit
{
    public string Id = "";
    public string AssetPath = "";
    public string Name = "";
    public string AssetJson = "";
    public string Status = "pending";
    public List<string> OverrideLabels = new();
    public List<string> Errors = new();
    public List<VariantAudit> Variants = new();
}

internal sealed class VariantAudit
{
    public string Label = "";
    public string MontagePath = "";
    public List<string> AnimationPaths = new();
    public Dictionary<string, string> AnimationGraphs = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> SequenceEvidence = new(StringComparer.OrdinalIgnoreCase);
    public List<string> NotifyTypes = new();
    public List<string> NamedNotifies = new();
    public List<string> NotifyDetails = new();
    public List<string> PropEvidence = new();
    public List<string> Errors = new();
}

internal sealed class BatchSelection
{
    public string Source = "favorites";
    public string SourceRevision = "";
    public string AuditSha256 = "";
    public List<SelectedEmote> Items = new();
}

internal sealed class CatalogEntry
{
    public string Id = "";
    public string AssetPath = "";
    public string Name = "";
    public string Status = "pending";
    public string Error = "";
    public List<string> Tags = new();
}

internal sealed class SelectedEmote
{
    public string Id = "";
    public string Name = "";
    public string AssetPath = "";
    public string Status = "";
    public string AssetSha256 = "";
    public List<VariantAudit> Variants = new();
}

internal sealed class ExportRecord
{
    public string Id = "";
    public string Name = "";
    public string Status = "pending";
    public string Error = "";
    public List<VariantExportRecord> Variants = new();
}

internal sealed class VariantExportRecord
{
    public string Label = "";
    public string Montage = "";
    public int AudioReferences;
    public List<ExportedFile> Files = new();
}

internal sealed class ExportedFile
{
    public string Kind = "";
    public string Path = "";
    public string Sha256 = "";
    public long Bytes;
    public bool Reused;
}
