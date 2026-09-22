{
  description = "UTA transit explorer: GTFS + GTFS-realtime collector, SQLite history, dashboard";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      runtimeDeps = ps: with ps; [ fastapi uvicorn gtfs-realtime-bindings protobuf requests ];
    in
    {
      packages = forAll (pkgs: rec {
        uta = pkgs.python3Packages.buildPythonApplication {
          pname = "uta";
          version = "0.0.0";
          pyproject = true;
          src = ./.;
          build-system = [ pkgs.python3Packages.setuptools ];
          dependencies = runtimeDeps pkgs.python3Packages;
          nativeCheckInputs = with pkgs.python3Packages; [ pytestCheckHook httpx ];
        };
        default = uta;
      });

      # `nix run . -- up` (collector + dashboard), `nix run . -- collect`, etc.
      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.system}.uta}/bin/uta";
        };
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: runtimeDeps ps ++ [ ps.pytest ps.httpx ]))
            pkgs.sqlite
          ];
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
            export UTA_DB="''${UTA_DB:-$PWD/data/uta.db}"
            export TZ=America/Denver   # so sqlite3 'localtime' matches the app
          '';
        };
      });
    };
}
