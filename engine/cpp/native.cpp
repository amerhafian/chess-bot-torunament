// C++ bitboard search and the project's power-form eval.
// Move generation is Disservin's MIT chess library (engine/cpp/third_party/chess.hpp).
// The Python API stays in FastAPI; this module is the fast path for choose_move.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "chess.hpp"
#include "pst_tables.inc"

namespace py = pybind11;

namespace {

constexpr double kMate = 100000.0;
constexpr double kMateBound = kMate / 2.0;
constexpr int kMaxQ = 8;
constexpr int kNullR = 2;
constexpr int kMaxPly = 128;
constexpr int kBoundExact = 0;
constexpr int kBoundLower = 1;
constexpr int kBoundUpper = 2;

constexpr int kPieceValue[6] = {1, 3, 3, 5, 9, 0};

struct Weights {
    double coeff[14]{};
    double expn[14]{};

    static Weights parse(const std::vector<double>& v) {
        Weights w;
        for (int i = 0; i < 14; ++i) {
            w.coeff[i] = 0.0;
            w.expn[i] = 1.0;
        }
        w.coeff[0] = 1.0;
        if (v.size() == 3) {
            w.coeff[0] = v[0];
            w.coeff[1] = v[1];
            w.coeff[2] = v[2];
        } else if (v.size() == 10 || v.size() >= 22) {
            for (int i = 0; i < 5; ++i) {
                w.coeff[i] = v[i];
                w.expn[i] = v[5 + i];
            }
            if (v.size() >= 22) {
                for (int i = 0; i < 6; ++i) {
                    w.coeff[5 + i] = v[10 + i];
                    w.expn[5 + i] = v[16 + i];
                }
            }
            if (v.size() >= 28) {
                for (int i = 0; i < 3; ++i) {
                    w.coeff[11 + i] = v[22 + i];
                    w.expn[11 + i] = v[25 + i];
                }
            }
        } else {
            throw std::invalid_argument("expected 3, 10, 22, or 28 weights");
        }
        return w;
    }
};

double signed_pow(double value, double exp) {
    if (value == 0.0 || exp == 1.0) return value;
    double mag = std::pow(std::fabs(value), exp);
    return value > 0.0 ? mag : -mag;
}

double term(double coeff, double exp, double scaled) {
    if (coeff == 0.0 || scaled == 0.0) return 0.0;
    if (exp == 1.0) return coeff * scaled;
    return coeff * signed_pow(scaled, exp);
}

int pop_lsb(chess::Bitboard& bb) {
    int sq = bb.lsb();
    bb.clear(sq);
    return sq;
}

chess::Bitboard attacks_of(const chess::Board& board, int sq, chess::PieceType pt, chess::Color color) {
    chess::Square square(sq);
    chess::Bitboard occ = board.occ();
    if (pt == chess::PieceType::PAWN) return chess::attacks::pawn(color, square);
    if (pt == chess::PieceType::KNIGHT) return chess::attacks::knight(square);
    if (pt == chess::PieceType::BISHOP) return chess::attacks::bishop(square, occ);
    if (pt == chess::PieceType::ROOK) return chess::attacks::rook(square, occ);
    if (pt == chess::PieceType::QUEEN)
        return chess::attacks::bishop(square, occ) | chess::attacks::rook(square, occ);
    return chess::attacks::king(square);
}

struct AttackPack {
    int controlled = 0;
    int king = 0;
    int attacked = 0;
    int center = 0;
};

AttackPack side_attacks(const chess::Board& board, chess::Color color) {
    AttackPack pack;
    chess::Color enemy = ~color;
    chess::Square king = board.kingSq(enemy);
    chess::Bitboard ring = chess::attacks::king(king) | chess::Bitboard::fromSquare(king);
    chess::Bitboard enemy_occ = board.us(enemy);
    constexpr chess::Bitboard kCenter{0x0000001818000000ULL};  // d4 d5 e4 e5
    chess::Bitboard attack_union{0};
    const chess::PieceType types[] = {chess::PieceType::PAWN,   chess::PieceType::KNIGHT, chess::PieceType::BISHOP,
                                      chess::PieceType::ROOK,   chess::PieceType::QUEEN,  chess::PieceType::KING};
    for (chess::PieceType pt : types) {
        chess::Bitboard bb = board.pieces(pt, color);
        while (bb) {
            int sq = pop_lsb(bb);
            chess::Bitboard attacks = attacks_of(board, sq, pt, color);
            pack.controlled += attacks.count();
            pack.king += (attacks & ring).count();
            pack.center += (attacks & kCenter).count();
            attack_union |= attacks;
        }
    }
    pack.attacked = (attack_union & enemy_occ).count();
    return pack;
}

double game_phase(const chess::Board& board) {
    int units = 0;
    auto add = [&](chess::PieceType pt, int w) {
        units += w * (board.pieces(pt, chess::Color::WHITE).count() + board.pieces(pt, chess::Color::BLACK).count());
    };
    add(chess::PieceType::KNIGHT, 1);
    add(chess::PieceType::BISHOP, 1);
    add(chess::PieceType::ROOK, 2);
    add(chess::PieceType::QUEEN, 4);
    if (units >= 24) return 1.0;
    return units / 24.0;
}

const int* pst_table(bool mg, chess::PieceType pt) {
    if (pt == chess::PieceType::PAWN) return mg ? PST_MG_PAWN : PST_EG_PAWN;
    if (pt == chess::PieceType::KNIGHT) return mg ? PST_MG_KNIGHT : PST_EG_KNIGHT;
    if (pt == chess::PieceType::BISHOP) return mg ? PST_MG_BISHOP : PST_EG_BISHOP;
    if (pt == chess::PieceType::ROOK) return mg ? PST_MG_ROOK : PST_EG_ROOK;
    if (pt == chess::PieceType::QUEEN) return mg ? PST_MG_QUEEN : PST_EG_QUEEN;
    return mg ? PST_MG_KING : PST_EG_KING;
}

double pst_balance(const chess::Board& board, double phase) {
    double endgame = 1.0 - phase;
    double score = 0.0;
    const chess::PieceType types[] = {chess::PieceType::PAWN,   chess::PieceType::KNIGHT, chess::PieceType::BISHOP,
                                      chess::PieceType::ROOK,   chess::PieceType::QUEEN,  chess::PieceType::KING};
    for (chess::Color color : {chess::Color::WHITE, chess::Color::BLACK}) {
        double sign = color == chess::Color::WHITE ? 1.0 : -1.0;
        for (chess::PieceType pt : types) {
            const int* mg = pst_table(true, pt);
            const int* eg = pst_table(false, pt);
            chess::Bitboard bb = board.pieces(pt, color);
            while (bb) {
                int sq = pop_lsb(bb);
                int idx = color == chess::Color::WHITE ? (sq ^ 56) : sq;
                score += sign * (phase * mg[idx] + endgame * eg[idx]);
            }
        }
    }
    return score / 100.0;
}

bool is_passed(const chess::Board& board, int sq, chess::Color color) {
    int file = sq & 7;
    int rank = sq >> 3;
    chess::Color enemy = ~color;
    for (int df = -1; df <= 1; ++df) {
        int f = file + df;
        if (f < 0 || f > 7) continue;
        if (color == chess::Color::WHITE) {
            for (int r = rank + 1; r < 8; ++r) {
                auto piece = board.at(chess::Square(f + r * 8));
                if (piece != chess::Piece::NONE && piece.type() == chess::PieceType::PAWN && piece.color() == enemy)
                    return false;
            }
        } else {
            for (int r = rank - 1; r >= 0; --r) {
                auto piece = board.at(chess::Square(f + r * 8));
                if (piece != chess::Piece::NONE && piece.type() == chess::PieceType::PAWN && piece.color() == enemy)
                    return false;
            }
        }
    }
    return true;
}

double passed_balance(const chess::Board& board, double phase) {
    constexpr double bonus[8] = {0.0, 0.05, 0.10, 0.20, 0.35, 0.60, 1.00, 1.50};
    double scale = 0.5 + 1.5 * (1.0 - phase);
    double total = 0.0;
    for (chess::Color color : {chess::Color::WHITE, chess::Color::BLACK}) {
        double sign = color == chess::Color::WHITE ? 1.0 : -1.0;
        chess::Bitboard bb = board.pieces(chess::PieceType::PAWN, color);
        while (bb) {
            int sq = pop_lsb(bb);
            if (!is_passed(board, sq, color)) continue;
            int rank = sq >> 3;
            int advance = color == chess::Color::WHITE ? rank : 7 - rank;
            total += sign * bonus[advance] * scale;
        }
    }
    return total;
}

double structure_balance(const chess::Board& board) {
    auto penalty = [&](chess::Color color) {
        int files[8] = {};
        chess::Bitboard bb = board.pieces(chess::PieceType::PAWN, color);
        while (bb) {
            int sq = pop_lsb(bb);
            files[sq & 7] += 1;
        }
        int doubled = 0;
        int isolated = 0;
        for (int f = 0; f < 8; ++f) {
            if (files[f] >= 2) doubled += files[f] - 1;
            if (files[f] == 0) continue;
            int left = f > 0 ? files[f - 1] : 0;
            int right = f < 7 ? files[f + 1] : 0;
            if (left == 0 && right == 0) isolated += files[f];
        }
        return doubled + isolated;
    };
    return static_cast<double>(penalty(chess::Color::BLACK) - penalty(chess::Color::WHITE));
}

double shield_balance(const chess::Board& board) {
    auto score = [&](chess::Color color) {
        chess::Square king = board.kingSq(color);
        int kfile = king.index() & 7;
        int krank = king.index() >> 3;
        int direction = color == chess::Color::WHITE ? 1 : -1;
        int pawns = 0;
        for (int df = -1; df <= 1; ++df) {
            int file = kfile + df;
            if (file < 0 || file > 7) continue;
            for (int step = 1; step <= 2; ++step) {
                int rank = krank + direction * step;
                if (rank < 0 || rank > 7) continue;
                auto piece = board.at(chess::Square(file + rank * 8));
                if (piece != chess::Piece::NONE && piece.type() == chess::PieceType::PAWN && piece.color() == color)
                    ++pawns;
            }
        }
        chess::Bitboard ring = chess::attacks::king(king) | chess::Bitboard::fromSquare(king);
        int heavies = 0;
        chess::Color enemy = ~color;
        for (chess::PieceType pt : {chess::PieceType::QUEEN, chess::PieceType::ROOK}) {
            chess::Bitboard bb = board.pieces(pt, enemy);
            while (bb) {
                int sq = pop_lsb(bb);
                if (attacks_of(board, sq, pt, enemy) & ring) ++heavies;
            }
        }
        return static_cast<double>(pawns) - 0.75 * heavies;
    };
    return score(chess::Color::WHITE) - score(chess::Color::BLACK);
}

int bishop_balance(const chess::Board& board) {
    int white = board.pieces(chess::PieceType::BISHOP, chess::Color::WHITE).count() >= 2 ? 1 : 0;
    int black = board.pieces(chess::PieceType::BISHOP, chess::Color::BLACK).count() >= 2 ? 1 : 0;
    return white - black;
}

int rook_balance(const chess::Board& board) {
    chess::Bitboard all_pawns =
        board.pieces(chess::PieceType::PAWN, chess::Color::WHITE) | board.pieces(chess::PieceType::PAWN, chess::Color::BLACK);
    auto score = [&](chess::Color color) {
        chess::Bitboard friendly = board.pieces(chess::PieceType::PAWN, color);
        int total = 0;
        chess::Bitboard bb = board.pieces(chess::PieceType::ROOK, color);
        while (bb) {
            int sq = pop_lsb(bb);
            chess::Bitboard mask(chess::File(sq & 7));
            if (friendly & mask) continue;
            total += (all_pawns & mask) ? 1 : 2;
        }
        return total;
    };
    return score(chess::Color::WHITE) - score(chess::Color::BLACK);
}

bool pawn_attacks_square(const chess::Board& board, int sq, chess::Color color) {
    chess::Bitboard origins = chess::attacks::pawn(~color, chess::Square(sq));
    return static_cast<bool>(board.pieces(chess::PieceType::PAWN, color) & origins);
}

double tempo_balance(const chess::Board& board) {
    return board.sideToMove() == chess::Color::WHITE ? 1.0 : -1.0;
}

int outpost_balance(const chess::Board& board) {
    auto count = [&](chess::Color color) {
        int total = 0;
        chess::Bitboard bb = board.pieces(chess::PieceType::KNIGHT, color);
        while (bb) {
            int sq = pop_lsb(bb);
            int rank = sq >> 3;
            if (color == chess::Color::WHITE) {
                if (rank < 3 || rank > 5) continue;
            } else if (rank < 2 || rank > 4) {
                continue;
            }
            if (!pawn_attacks_square(board, sq, color)) continue;
            if (pawn_attacks_square(board, sq, ~color)) continue;
            ++total;
        }
        return total;
    };
    return count(chess::Color::WHITE) - count(chess::Color::BLACK);
}

int tropism_balance(const chess::Board& board) {
    auto score = [&](chess::Color color) {
        int king = board.kingSq(~color).index();
        int total = 0;
        const chess::PieceType types[] = {chess::PieceType::QUEEN, chess::PieceType::ROOK, chess::PieceType::KNIGHT};
        for (chess::PieceType pt : types) {
            chess::Bitboard bb = board.pieces(pt, color);
            while (bb) {
                int sq = pop_lsb(bb);
                int df = std::abs((sq & 7) - (king & 7));
                int dr = std::abs((sq >> 3) - (king >> 3));
                total += 7 - std::max(df, dr);
            }
        }
        return total;
    };
    return score(chess::Color::WHITE) - score(chess::Color::BLACK);
}

int material_balance(const chess::Board& board) {
    int score = 0;
    const chess::PieceType types[] = {chess::PieceType::PAWN, chess::PieceType::KNIGHT, chess::PieceType::BISHOP,
                                      chess::PieceType::ROOK, chess::PieceType::QUEEN};
    for (chess::PieceType pt : types) {
        int value = kPieceValue[static_cast<int>(pt)];
        score += value * (board.pieces(pt, chess::Color::WHITE).count() - board.pieces(pt, chess::Color::BLACK).count());
    }
    return score;
}

double static_eval(const chess::Board& board, const Weights& w) {
    double score = term(w.coeff[0], w.expn[0], static_cast<double>(material_balance(board)));
    if (w.coeff[1] != 0.0 || w.coeff[2] != 0.0 || w.coeff[3] != 0.0 || w.coeff[4] != 0.0) {
        AttackPack white = side_attacks(board, chess::Color::WHITE);
        AttackPack black = side_attacks(board, chess::Color::BLACK);
        score += term(w.coeff[1], w.expn[1], (white.controlled - black.controlled) / 20.0);
        score += term(w.coeff[2], w.expn[2], (white.king - black.king) / 4.0);
        score += term(w.coeff[3], w.expn[3], (white.attacked - black.attacked) / 2.0);
        score += term(w.coeff[4], w.expn[4], (white.center - black.center) / 4.0);
    }
    if (w.coeff[5] || w.coeff[6] || w.coeff[7] || w.coeff[8] || w.coeff[9] || w.coeff[10]) {
        double phase = game_phase(board);
        score += term(w.coeff[5], w.expn[5], pst_balance(board, phase));
        score += term(w.coeff[6], w.expn[6], passed_balance(board, phase));
        score += term(w.coeff[7], w.expn[7], structure_balance(board));
        score += term(w.coeff[8], w.expn[8], shield_balance(board));
        score += term(w.coeff[9], w.expn[9], static_cast<double>(bishop_balance(board)));
        score += term(w.coeff[10], w.expn[10], static_cast<double>(rook_balance(board)));
    }
    if (w.coeff[11] != 0.0 || w.coeff[12] != 0.0 || w.coeff[13] != 0.0) {
        score += term(w.coeff[11], w.expn[11], tempo_balance(board));
        score += term(w.coeff[12], w.expn[12], static_cast<double>(outpost_balance(board)));
        score += term(w.coeff[13], w.expn[13], tropism_balance(board) / 4.0);
    }
    return score;
}

bool is_draw(const chess::Board& board) {
    if (board.isInsufficientMaterial()) return true;
    if (board.halfMoveClock() >= 100) return true;
    if (board.halfMoveClock() >= 4 && board.isRepetition(2)) return true;
    return false;
}

double pack_mate(double score, int ply) {
    if (score > kMateBound) return score + ply;
    if (score < -kMateBound) return score - ply;
    return score;
}

double unpack_mate(double score, int ply) {
    if (score > kMateBound) return score - ply;
    if (score < -kMateBound) return score + ply;
    return score;
}

struct TTSlot {
    std::atomic<std::uint64_t> key{0};
    std::atomic<std::uint64_t> meta{0};
};

std::uint64_t pack_meta(int depth, int bound, std::uint16_t move, double score) {
    float narrowed = static_cast<float>(score);
    std::uint32_t score_bits = 0;
    std::memcpy(&score_bits, &narrowed, sizeof(score_bits));
    return (static_cast<std::uint64_t>(depth & 0xffff)) | (static_cast<std::uint64_t>(bound & 0xff) << 16) |
           (static_cast<std::uint64_t>(move) << 24) | (static_cast<std::uint64_t>(score_bits) << 32);
}

void unpack_meta(std::uint64_t meta, int& depth, int& bound, std::uint16_t& move, double& score) {
    depth = static_cast<int>(meta & 0xffff);
    bound = static_cast<int>((meta >> 16) & 0xff);
    move = static_cast<std::uint16_t>((meta >> 24) & 0xffff);
    std::uint32_t score_bits = static_cast<std::uint32_t>(meta >> 32);
    float narrowed = 0;
    std::memcpy(&narrowed, &score_bits, sizeof(narrowed));
    score = narrowed;
}

struct SharedTT {
    std::unique_ptr<TTSlot[]> entries;
    std::size_t size;
    explicit SharedTT(std::size_t n = 1 << 20) : entries(new TTSlot[n]), size(n) {}
};

struct Search {
    chess::Board& board;
    const Weights& weights;
    SharedTT* tt;
    chess::Move killers[kMaxPly][2]{};
    int history[2][64][64]{};

    bool has_non_pawn(chess::Color color) const {
        return board.pieces(chess::PieceType::KNIGHT, color) || board.pieces(chess::PieceType::BISHOP, color) ||
               board.pieces(chess::PieceType::ROOK, color) || board.pieces(chess::PieceType::QUEEN, color);
    }

    int mvv_lva(const chess::Move& move) const {
        int victim = 0;
        if (move.typeOf() == chess::Move::ENPASSANT) {
            victim = 1;
        } else {
            auto captured = board.at(move.to());
            if (captured != chess::Piece::NONE && move.typeOf() != chess::Move::CASTLING) victim = kPieceValue[int(captured.type())];
        }
        int attacker = kPieceValue[int(board.at(move.from()).type())];
        int promo = 0;
        if (move.typeOf() == chess::Move::PROMOTION) promo = kPieceValue[int(move.promotionType())] * 4;
        return victim * 16 - attacker + promo;
    }

    void clear_heuristics() {
        for (int ply = 0; ply < kMaxPly; ++ply) {
            killers[ply][0] = chess::Move(0);
            killers[ply][1] = chess::Move(0);
        }
        std::memset(history, 0, sizeof(history));
    }

    void order_moves(chess::Movelist& moves, const chess::Move* tt_move, int ply) const {
        std::vector<std::pair<int, chess::Move>> ranked;
        ranked.reserve(static_cast<std::size_t>(moves.size()));
        int side = int(board.sideToMove());
        for (const auto& move : moves) {
            int score = history[side][move.from().index()][move.to().index()];
            if (tt_move && *tt_move != chess::Move(0) && move == *tt_move) score = 2000000;
            else if (board.isCapture(move) || move.typeOf() == chess::Move::PROMOTION)
                score = 1000000 + mvv_lva(move);
            else if (ply < kMaxPly && killers[ply][0] != chess::Move(0) && move == killers[ply][0])
                score = 800000;
            else if (ply < kMaxPly && killers[ply][1] != chess::Move(0) && move == killers[ply][1])
                score = 700000;
            ranked.emplace_back(score, move);
        }
        std::stable_sort(ranked.begin(), ranked.end(),
                         [](const auto& a, const auto& b) { return a.first > b.first; });
        moves.clear();
        for (const auto& item : ranked) moves.add(item.second);
    }

    void remember(const chess::Move& move, int ply, int depth) {
        if (board.isCapture(move) || move.typeOf() == chess::Move::PROMOTION) return;
        if (ply >= kMaxPly) return;
        if (killers[ply][0] != move) {
            killers[ply][1] = killers[ply][0];
            killers[ply][0] = move;
        }
        history[int(board.sideToMove())][move.from().index()][move.to().index()] += depth * depth;
    }

    bool probe(int depth, double& alpha, double& beta, int ply, chess::Move& tt_move, double& hit) {
        hit = 0;
        if (!tt) return false;
        TTSlot& e = tt->entries[board.hash() & (tt->size - 1)];
        std::uint64_t meta = e.meta.load(std::memory_order_acquire);
        if (meta == 0) return false;
        std::uint64_t key = e.key.load(std::memory_order_acquire);
        if (e.meta.load(std::memory_order_acquire) != meta) return false;
        if (key != board.hash()) return false;
        int stored_depth = 0;
        int bound = 0;
        std::uint16_t move_bits = 0;
        double stored = 0;
        unpack_meta(meta, stored_depth, bound, move_bits, stored);
        tt_move = chess::Move(move_bits);
        if (stored_depth < depth) return false;
        double score = unpack_mate(stored, ply);
        if (bound == kBoundExact) {
            hit = score;
            return true;
        }
        if (bound == kBoundLower) alpha = std::max(alpha, score);
        else if (bound == kBoundUpper) beta = std::min(beta, score);
        if (alpha >= beta) {
            hit = score;
            return true;
        }
        return false;
    }

    void store(int depth, double value, double alpha_orig, double beta, int ply, const chess::Move* best) {
        if (!tt) return;
        std::uint8_t bound = kBoundExact;
        if (value <= alpha_orig) bound = kBoundUpper;
        else if (value >= beta) bound = kBoundLower;
        TTSlot& e = tt->entries[board.hash() & (tt->size - 1)];
        std::uint64_t old_meta = e.meta.load(std::memory_order_acquire);
        std::uint64_t old_key = e.key.load(std::memory_order_acquire);
        if (old_meta != 0 && old_key != board.hash()) {
            int old_depth = static_cast<int>(old_meta & 0xffff);
            if (old_depth > depth) return;
        }
        std::uint64_t meta = pack_meta(depth, bound, best ? best->move() : 0, pack_mate(value, ply));
        e.meta.store(0, std::memory_order_relaxed);
        e.key.store(board.hash(), std::memory_order_relaxed);
        e.meta.store(meta, std::memory_order_release);
    }

    bool see_non_negative(const chess::Move& move) const {
        int victim = 0;
        if (move.typeOf() == chess::Move::ENPASSANT) {
            victim = 1;
        } else {
            auto captured = board.at(move.to());
            if (captured != chess::Piece::NONE && move.typeOf() != chess::Move::CASTLING)
                victim = kPieceValue[int(captured.type())];
        }
        if (move.typeOf() == chess::Move::PROMOTION) victim += kPieceValue[int(move.promotionType())] - 1;
        int attacker = kPieceValue[int(board.at(move.from()).type())];
        if (!board.isAttacked(move.to(), ~board.sideToMove())) return true;
        return victim >= attacker;
    }

    int victim_value(const chess::Move& move) const {
        int victim = 0;
        if (move.typeOf() == chess::Move::ENPASSANT) {
            victim = 1;
        } else {
            auto captured = board.at(move.to());
            if (captured != chess::Piece::NONE && move.typeOf() != chess::Move::CASTLING)
                victim = kPieceValue[int(captured.type())];
        }
        if (move.typeOf() == chess::Move::PROMOTION) victim += kPieceValue[int(move.promotionType())] - 1;
        return victim;
    }

    double mate_score(int ply) const {
        double plies = std::max(0, ply);
        if (board.sideToMove() == chess::Color::WHITE) return -(kMate - plies);
        return kMate - plies;
    }

    double quiescence(double alpha, double beta, int ply, int qply) {
        if (is_draw(board)) return 0.0;
        bool in_check = board.inCheck();
        double stand = 0;
        bool have_stand = false;
        bool white = board.sideToMove() == chess::Color::WHITE;
        if (!in_check) {
            stand = static_eval(board, weights);
            have_stand = true;
            if (white) {
                if (stand >= beta) return stand;
                if (stand > alpha) alpha = stand;
            } else {
                if (stand <= alpha) return stand;
                if (stand < beta) beta = stand;
            }
        }
        if (qply >= kMaxQ) return have_stand ? stand : static_eval(board, weights);

        chess::Movelist moves;
        if (in_check) {
            chess::movegen::legalmoves(moves, board);
        } else {
            chess::Movelist captures;
            chess::movegen::legalmoves<chess::movegen::MoveGenType::CAPTURE>(captures, board);
            for (const auto& move : captures) {
                if (see_non_negative(move)) moves.add(move);
            }
            chess::Movelist quiets;
            chess::movegen::legalmoves<chess::movegen::MoveGenType::QUIET>(quiets, board);
            for (const auto& move : quiets) {
                if (move.typeOf() == chess::Move::PROMOTION && move.promotionType() == chess::PieceType::QUEEN)
                    moves.add(move);
            }
        }
        order_moves(moves, nullptr, ply);
        if (moves.empty()) {
            if (in_check) return mate_score(ply);
            return have_stand ? stand : 0.0;
        }
        double value = white ? (have_stand ? stand : -1e30) : (have_stand ? stand : 1e30);
        for (const auto& move : moves) {
            if (have_stand && !in_check) {
                double victim = static_cast<double>(victim_value(move));
                if (white && stand + victim + 1.0 < alpha) continue;
                if (!white && stand - victim - 1.0 > beta) continue;
            }
            board.makeMove(move);
            double score = quiescence(alpha, beta, ply + 1, qply + 1);
            board.unmakeMove(move);
            if (white) {
                if (score > value) value = score;
                alpha = std::max(alpha, value);
            } else {
                if (score < value) value = score;
                beta = std::min(beta, value);
            }
            if (alpha >= beta) break;
        }
        return value;
    }

    double alphabeta(int depth, double alpha, double beta, int ply, int extensions = 0, bool in_null = false) {
        if (is_draw(board)) return 0.0;
        double alpha_orig = alpha;
        chess::Move tt_move = chess::Move(0);
        double tt_hit = 0;
        bool have_tt = probe(depth, alpha, beta, ply, tt_move, tt_hit);
        chess::Move* tt_ptr = tt_move.move() != 0 ? &tt_move : nullptr;
        if (have_tt) return tt_hit;
        double beta_orig = beta;
        if (depth <= 0) return quiescence(alpha, beta, ply, 0);

        bool in_check = board.inCheck();
        chess::Movelist moves;
        chess::movegen::legalmoves(moves, board);
        order_moves(moves, tt_ptr, ply);
        if (moves.empty()) {
            if (in_check) return mate_score(ply);
            return 0.0;
        }

        bool white = board.sideToMove() == chess::Color::WHITE;
        if (depth >= 3 && !in_check && !in_null && has_non_pawn(board.sideToMove())) {
            if (white && beta < kMateBound) {
                board.makeNullMove();
                double null_score = alphabeta(depth - 1 - kNullR, beta - 0.01, beta, ply + 1, extensions, true);
                board.unmakeNullMove();
                if (null_score >= beta) return null_score;
            } else if (!white && alpha > -kMateBound) {
                board.makeNullMove();
                double null_score = alphabeta(depth - 1 - kNullR, alpha, alpha + 0.01, ply + 1, extensions, true);
                board.unmakeNullMove();
                if (null_score <= alpha) return null_score;
            }
        }

        int extension = (in_check && extensions < 2) ? 1 : 0;
        int child_depth = depth - 1 + extension;
        int next_ext = extensions + extension;

        double value = white ? -1e30 : 1e30;
        chess::Move best = moves[0];
        bool have_best = false;
        int index = 0;
        for (const auto& move : moves) {
            bool noisy = board.isCapture(move) || move.typeOf() == chess::Move::PROMOTION;
            int reduction = (depth >= 3 && index >= 3 && !noisy && !in_check) ? 1 : 0;
            board.makeMove(move);
            double score;
            if (reduction && white && alpha > -kMateBound) {
                score = alphabeta(child_depth - reduction, alpha, alpha + 0.01, ply + 1, next_ext, false);
                if (score > alpha) score = alphabeta(child_depth, alpha, beta, ply + 1, next_ext, false);
            } else if (reduction && !white && beta < kMateBound) {
                score = alphabeta(child_depth - reduction, beta - 0.01, beta, ply + 1, next_ext, false);
                if (score < beta) score = alphabeta(child_depth, alpha, beta, ply + 1, next_ext, false);
            } else {
                score = alphabeta(child_depth, alpha, beta, ply + 1, next_ext, false);
            }
            board.unmakeMove(move);
            if (white) {
                if (score > value) {
                    value = score;
                    best = move;
                    have_best = true;
                }
                alpha = std::max(alpha, value);
            } else {
                if (score < value) {
                    value = score;
                    best = move;
                    have_best = true;
                }
                beta = std::min(beta, value);
            }
            if (alpha >= beta) {
                remember(move, ply, depth);
                break;
            }
            ++index;
        }
        store(depth, value, alpha_orig, beta_orig, ply, have_best ? &best : nullptr);
        return value;
    }
};

long perft_node(chess::Board& board, int depth) {
    chess::Movelist moves;
    chess::movegen::legalmoves(moves, board);
    if (depth == 1) return moves.size();
    long nodes = 0;
    for (const auto& move : moves) {
        board.makeMove(move);
        nodes += perft_node(board, depth - 1);
        board.unmakeMove(move);
    }
    return nodes;
}

std::pair<std::string, double> search_root(chess::Board board, const Weights& weights, int depth, int threads) {
    SharedTT tt;
    Search search{board, weights, &tt};
    search.clear_heuristics();
    chess::Move best{};
    double score = 0;
    bool white = board.sideToMove() == chess::Color::WHITE;
    for (int current = 1; current <= depth; ++current) {
        double alpha = current >= 4 ? score - 1.25 : -1e30;
        double beta = current >= 4 ? score + 1.25 : 1e30;
        chess::Move iter_best = best;
        double iter_score = score;
        for (int attempt = 0; attempt < 3; ++attempt) {
            chess::Movelist moves;
            chess::movegen::legalmoves(moves, board);
            chess::Move pv = iter_best;
            search.order_moves(moves, pv.move() ? &pv : nullptr, 0);
            double window_alpha = alpha;
            double window_beta = beta;
            double alpha_orig = alpha;
            double beta_orig = beta;
            double best_score = white ? -1e30 : 1e30;
            chess::Move chosen = moves[0];
            auto consider = [&](const chess::Move& move, double value) {
                if (white) {
                    if (value > best_score) {
                        best_score = value;
                        chosen = move;
                    }
                    window_alpha = std::max(window_alpha, best_score);
                } else {
                    if (value < best_score) {
                        best_score = value;
                        chosen = move;
                    }
                    window_beta = std::min(window_beta, best_score);
                }
            };
            board.makeMove(moves[0]);
            consider(moves[0], search.alphabeta(current - 1, window_alpha, window_beta, 1));
            board.unmakeMove(moves[0]);

            bool parallel = threads != 1 && current == depth && moves.size() >= 4 && current >= 3;
            if (parallel && window_alpha < window_beta) {
                std::vector<std::thread> workers;
                std::vector<double> scores(moves.size(), 1e30);
                std::mutex score_mu;
                unsigned nthreads = threads > 0 ? static_cast<unsigned>(threads)
                                                 : std::max(1u, std::thread::hardware_concurrency());
                std::size_t cursor = 1;
                std::mutex cursor_mu;
                auto worker = [&]() {
                    while (true) {
                        std::size_t i;
                        {
                            std::lock_guard<std::mutex> lock(cursor_mu);
                            if (cursor >= moves.size()) return;
                            i = cursor++;
                        }
                        chess::Board copy = board;
                        Search local{copy, weights, &tt};
                        local.clear_heuristics();
                        copy.makeMove(moves[i]);
                        double value = local.alphabeta(current - 1, window_alpha, window_beta, 1);
                        std::lock_guard<std::mutex> lock(score_mu);
                        scores[i] = value;
                    }
                };
                unsigned nworkers = std::min<unsigned>(nthreads, static_cast<unsigned>(moves.size() - 1));
                for (unsigned t = 0; t < nworkers; ++t) workers.emplace_back(worker);
                for (auto& th : workers) th.join();
                for (std::size_t i = 1; i < moves.size(); ++i) {
                    if (scores[i] >= 1e29) continue;
                    consider(moves[i], scores[i]);
                }
            } else {
                for (int i = 1; i < moves.size(); ++i) {
                    if (window_alpha >= window_beta) break;
                    board.makeMove(moves[i]);
                    double value = search.alphabeta(current - 1, window_alpha, window_beta, 1);
                    board.unmakeMove(moves[i]);
                    consider(moves[i], value);
                }
            }
            iter_best = chosen;
            iter_score = best_score;
            search.store(current, best_score, alpha_orig, beta_orig, 0, &chosen);
            if (iter_score <= alpha) {
                alpha = -1e30;
            } else if (iter_score >= beta) {
                beta = 1e30;
            } else {
                break;
            }
        }
        best = iter_best;
        score = iter_score;
    }
    return {chess::uci::moveToUci(best), score};
}

}  // namespace

PYBIND11_MODULE(native, m) {
    m.doc() = "Bitboard alpha-beta with the tournament power-form eval";
    m.def("perft", [](const std::string& fen, int depth) {
        chess::Board board(fen);
        if (depth <= 0) return 1L;
        return perft_node(board, depth);
    });
    m.def("evaluate_fen", [](const std::string& fen, const std::vector<double>& weights) {
        chess::Board board(fen);
        return static_eval(board, Weights::parse(weights));
    });
    m.def(
        "choose_move",
        [](const std::string& fen, const std::vector<double>& weights, int depth, int threads) {
            if (depth < 1) depth = 1;
            chess::Board board(fen);
            chess::Movelist moves;
            chess::movegen::legalmoves(moves, board);
            if (moves.empty()) throw std::runtime_error("no legal moves");
            std::string uci;
            double score = 0;
            {
                py::gil_scoped_release release;
                auto result = search_root(board, Weights::parse(weights), depth, threads);
                uci = result.first;
                score = result.second;
            }
            return py::make_tuple(uci, score);
        },
        py::arg("fen"),
        py::arg("weights"),
        py::arg("depth"),
        py::arg("threads") = 0);
}
